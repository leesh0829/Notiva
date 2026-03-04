from __future__ import annotations

import json
import math

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import QAMessage, TranscriptChunk
from app.schemas.qa import QAResponse
from app.services.embedding import embed_text
from app.services.openai_client import get_openai_client


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


def _rank_chunks(db: Session, recording_id: str, question: str) -> list[dict]:
    q_embedding = embed_text(question)

    # Postgres + pgvector path: do top-k search in DB.
    if settings.database_url.startswith("postgresql") and hasattr(TranscriptChunk.embedding, "cosine_distance"):
        try:
            distance = TranscriptChunk.embedding.cosine_distance(q_embedding)
            rows = (
                db.query(TranscriptChunk, distance.label("distance"))
                .filter(TranscriptChunk.recording_id == recording_id)
                .order_by(distance.asc())
                .limit(settings.rag_top_k)
                .all()
            )
            if rows:
                return [
                    {"chunk": row[0], "score": max(0.0, 1.0 - float(row[1]))}
                    for row in rows
                ]
        except Exception:
            # Fallback to Python scoring when DB vector op is unavailable.
            pass

    chunks = (
        db.query(TranscriptChunk)
        .filter(TranscriptChunk.recording_id == recording_id)
        .order_by(TranscriptChunk.chunk_index.asc())
        .all()
    )
    scored = [{"chunk": chunk, "score": _cosine_similarity(q_embedding, chunk.embedding)} for chunk in chunks]
    return sorted(scored, key=lambda item: item["score"], reverse=True)[: settings.rag_top_k]


def _fallback_answer(top: list[dict]) -> str:
    lines = [item["chunk"].content for item in top]
    return "\n".join(f"- {line}" for line in lines)


def _llm_answer(question: str, top: list[dict], recent_turns: list[QAMessage]) -> tuple[str, list[int]]:
    client = get_openai_client()
    if client is None:
        return _fallback_answer(top), list(range(len(top)))

    lines: list[str] = []
    used_chars = 0
    for idx, item in enumerate(top):
        line = f"[{idx}] ({item['chunk'].start_ms}-{item['chunk'].end_ms}ms) {item['chunk'].content}"
        projected = used_chars + len(line) + (1 if lines else 0)
        if projected > settings.qa_max_context_chars and lines:
            break
        lines.append(line)
        used_chars = projected
    context = "\n".join(lines)
    history_lines: list[str] = []
    for turn in recent_turns:
        q = turn.question[: settings.qa_history_chars_per_turn]
        a = turn.answer[: settings.qa_history_chars_per_turn]
        history_lines.append(f"Q: {q}\nA: {a}")
    history_text = "\n\n".join(history_lines)

    completion = client.chat.completions.create(
        model=settings.openai_chat_model,
        response_format={"type": "json_object"},
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer only from the provided transcript context.\n"
                    "Return JSON with keys: answer (string), citation_indexes (int array).\n"
                    "citation_indexes must contain indices of used context lines."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Recent conversation (latest first, optional):\n{history_text or '(none)'}\n\n"
                    f"Question:\n{question}\n\nContext:\n{context}"
                ),
            },
        ],
    )
    content = completion.choices[0].message.content or "{}"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {"answer": content, "citation_indexes": list(range(len(top)))}
    answer = str(payload.get("answer", "")).strip() or _fallback_answer(top)
    idx_values = payload.get("citation_indexes", [])
    picked = [int(idx) for idx in idx_values if isinstance(idx, int) and 0 <= idx < len(top)]
    if not picked:
        picked = list(range(len(top)))
    return answer, picked


def answer_question(db: Session, recording_id: str, user_id: str, question: str) -> QAResponse:
    chunk_count = (
        db.query(TranscriptChunk)
        .filter(TranscriptChunk.recording_id == recording_id)
        .count()
    )
    if chunk_count == 0:
        raise ValueError("Transcript index not ready")

    top = _rank_chunks(db, recording_id, question)
    recent_turns = (
        db.query(QAMessage)
        .filter(QAMessage.recording_id == recording_id, QAMessage.user_id == user_id)
        .order_by(QAMessage.created_at.desc())
        .limit(settings.qa_history_turns)
        .all()
    )
    answer, picked = _llm_answer(question, top, recent_turns)
    citations = [
        {
            "chunk_id": top[idx]["chunk"].id,
            "text": top[idx]["chunk"].content,
            "start_ms": top[idx]["chunk"].start_ms,
            "end_ms": top[idx]["chunk"].end_ms,
            "score": round(top[idx]["score"], 4),
        }
        for idx in picked
    ]

    db.add(
        QAMessage(
            recording_id=recording_id,
            user_id=user_id,
            question=question,
            answer=answer,
            citations=citations,
            model_name=settings.openai_chat_model if get_openai_client() else "fallback-rag-v1",
        )
    )
    db.commit()
    return QAResponse(answer=answer, citations=citations)
