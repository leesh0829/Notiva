from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Summary, Transcript
from app.services.chunking import chunk_transcript_segments
from app.services.openai_client import get_openai_client


def _fallback_summary(transcript: Transcript) -> tuple[str, list[dict], list[str], list[dict], str]:
    timeline = [{"time_ms": segment["start_ms"], "text": segment["text"]} for segment in transcript.segments[:6]]
    summary_md = (
        "## 회의 요약\n"
        "- 진행 상황 공유\n"
        "- 테스트 범위 및 액션 아이템 합의\n"
        "- 데모 전 API 통합 테스트 완료 결정"
    )
    action_items = [
        {"task": "통합 테스트 케이스 확정", "owner": "backend", "due": "2026-03-06"},
        {"task": "데모 시나리오 점검", "owner": "frontend", "due": "2026-03-07"},
    ]
    keywords = ["진행현황", "테스트", "액션아이템", "데모"]
    return summary_md, action_items, keywords, timeline, "fallback-summary-v1"


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        stripped = content.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(stripped)


def _safe_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _safe_chat_json(client, prompt: str, user_text: str) -> dict:
    completion = client.chat.completions.create(
        model=settings.openai_chat_model,
        response_format={"type": "json_object"},
        temperature=0.2,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    try:
        return _parse_json(content)
    except Exception:
        return {}


def _one_pass_summary(client, transcript_text: str) -> tuple[str, list[dict], list[str], list[dict]]:
    prompt = (
        "You are a meeting/class note assistant.\n"
        "Return JSON only with keys:\n"
        "summary_md (markdown), action_items (array of {task, owner, due}), "
        "keywords (string array), timeline (array of {time_ms, text}).\n"
        "Use Korean for summary_md and timeline text."
    )
    parsed = _safe_chat_json(client, prompt, transcript_text)
    summary_md = str(parsed.get("summary_md", "")).strip() or "요약을 생성하지 못했습니다."
    action_items = _safe_list(parsed.get("action_items"))
    keywords = [str(item) for item in _safe_list(parsed.get("keywords"))]
    timeline = _safe_list(parsed.get("timeline"))
    return summary_md, action_items, keywords, timeline


def _map_reduce_summary(transcript: Transcript, client) -> tuple[str, list[dict], list[str], list[dict]]:
    chunks = chunk_transcript_segments(
        transcript.segments,
        max_chars=settings.summary_map_chunk_chars,
        overlap_chars=0,
    )[: settings.summary_map_max_chunks]
    if not chunks:
        return _one_pass_summary(client, transcript.full_text[:4000])
    if len(chunks) == 1:
        return _one_pass_summary(client, chunks[0]["text"])

    map_prompt = (
        "You summarize one transcript chunk.\n"
        "Return JSON keys only: summary, action_items, keywords, timeline.\n"
        "action_items: array of {task, owner, due}, keywords: string array, "
        "timeline: array of {time_ms, text}. Keep concise Korean text."
    )
    mapped: list[dict] = []
    for chunk in chunks:
        chunk_text = str(chunk["text"])[: settings.summary_map_chunk_chars]
        parsed = _safe_chat_json(client, map_prompt, chunk_text)
        mapped.append(
            {
                "summary": str(parsed.get("summary", "")).strip(),
                "action_items": _safe_list(parsed.get("action_items")),
                "keywords": [str(item) for item in _safe_list(parsed.get("keywords"))],
                "timeline": _safe_list(parsed.get("timeline")),
            }
        )

    reduce_prompt = (
        "Merge chunk summaries into final output.\n"
        "Return JSON keys only: summary_md, action_items, keywords, timeline.\n"
        "summary_md must be markdown in Korean."
    )
    reduce_input = json.dumps({"chunk_summaries": mapped}, ensure_ascii=False)
    parsed = _safe_chat_json(client, reduce_prompt, reduce_input)
    summary_md = str(parsed.get("summary_md", "")).strip() or "요약을 생성하지 못했습니다."
    action_items = _safe_list(parsed.get("action_items"))
    keywords = [str(item) for item in _safe_list(parsed.get("keywords"))]
    timeline = _safe_list(parsed.get("timeline"))
    return summary_md, action_items, keywords, timeline


def run_summary(db: Session, recording_id: str) -> None:
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise ValueError("Transcript not found")

    client = get_openai_client()
    if client is None:
        summary_md, action_items, keywords, timeline, model_name = _fallback_summary(transcript)
    else:
        summary_md, action_items, keywords, timeline = _map_reduce_summary(transcript, client)
        model_name = settings.openai_chat_model

    summary = db.query(Summary).filter(Summary.recording_id == recording_id).first()
    if summary:
        summary.summary_md = summary_md
        summary.action_items = action_items
        summary.keywords = keywords
        summary.timeline = timeline
        summary.model_name = model_name
    else:
        db.add(
            Summary(
                recording_id=recording_id,
                summary_md=summary_md,
                action_items=action_items,
                keywords=keywords,
                timeline=timeline,
                model_name=model_name,
            )
        )
    db.commit()

