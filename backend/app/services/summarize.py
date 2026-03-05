from __future__ import annotations

import json

from openai import BadRequestError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Summary, Transcript
from app.services.chunking import chunk_transcript_segments
from app.services.openai_client import get_openai_client

SUMMARY_REDUCE_INPUT_MAX_CHARS = 6000


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


def _is_context_limit_error(exc: BadRequestError) -> bool:
    message = str(exc).lower()
    return "maximum context length" in message or "please reduce your prompt" in message


def _truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars < 40:
        return text[:max_chars]
    head = int(max_chars * 0.6)
    tail = max_chars - head - 17
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}"


def _compact_map_item(item: dict) -> dict:
    summary = str(item.get("summary", "")).strip()[:500]
    action_items = _safe_list(item.get("action_items"))[:8]
    keywords = [str(keyword).strip()[:40] for keyword in _safe_list(item.get("keywords"))[:15] if str(keyword).strip()]
    timeline_raw = _safe_list(item.get("timeline"))[:8]
    timeline: list[dict] = []
    for row in timeline_raw:
        if not isinstance(row, dict):
            continue
        timeline.append(
            {
                "time_ms": int(row.get("time_ms", 0) or 0),
                "text": str(row.get("text", "")).strip()[:120],
            }
        )
    return {
        "summary": summary,
        "action_items": action_items,
        "keywords": keywords,
        "timeline": timeline,
    }


def _bounded_reduce_input(mapped: list[dict]) -> str:
    compacted: list[dict] = []
    for raw_item in mapped:
        compact_item = _compact_map_item(raw_item)
        candidate = compacted + [compact_item]
        payload = json.dumps({"chunk_summaries": candidate}, ensure_ascii=False)
        if len(payload) > SUMMARY_REDUCE_INPUT_MAX_CHARS and compacted:
            break
        compacted = candidate
    if not compacted:
        compacted = [_compact_map_item(item) for item in mapped[:1]]
    return json.dumps({"chunk_summaries": compacted}, ensure_ascii=False)


def _safe_chat_json(client, prompt: str, user_text: str) -> dict:
    candidate = user_text
    for _ in range(5):
        try:
            completion = client.chat.completions.create(
                model=settings.openai_chat_model,
                response_format={"type": "json_object"},
                temperature=0.2,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": candidate},
                ],
            )
            content = completion.choices[0].message.content or "{}"
            try:
                return _parse_json(content)
            except Exception:
                return {}
        except BadRequestError as exc:
            if not _is_context_limit_error(exc):
                return {}
            next_limit = max(1000, int(len(candidate) * 0.7))
            if next_limit >= len(candidate):
                return {}
            candidate = _truncate_middle(candidate, next_limit)
        except Exception:
            return {}
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
    reduce_input = _bounded_reduce_input(mapped)
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

