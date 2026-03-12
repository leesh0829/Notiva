from __future__ import annotations

import json
import logging
import re

from openai import BadRequestError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Summary, Transcript
from app.services.chunking import chunk_transcript_segments
from app.services.openai_client import get_openai_client

SUMMARY_REDUCE_INPUT_MAX_CHARS = 18000
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")
logger = logging.getLogger(__name__)


def _safe_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _safe_text(value: object, max_chars: int = 1200) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:max_chars]


def _dedupe_texts(items: list[str], max_items: int, max_chars: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in items:
        text = _safe_text(raw, max_chars=max_chars)
        key = text.lower()
        if not text or key in seen:
            continue
        output.append(text)
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _safe_string_list(value: object, max_items: int = 12, max_chars: int = 240) -> list[str]:
    return _dedupe_texts([str(item) for item in _safe_list(value)], max_items=max_items, max_chars=max_chars)


def _safe_topic_summaries(value: object, max_items: int = 8) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for row in _safe_list(value):
        if not isinstance(row, dict):
            continue
        topic = _safe_text(row.get("topic"), max_chars=80)
        summary = _safe_text(row.get("summary"), max_chars=500)
        key = f"{topic.lower()}::{summary.lower()}"
        if not topic or not summary or key in seen:
            continue
        output.append({"topic": topic, "summary": summary})
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _safe_action_items(value: object, max_items: int = 12) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for row in _safe_list(value):
        if not isinstance(row, dict):
            continue
        task = _safe_text(row.get("task"), max_chars=200)
        owner = _safe_text(row.get("owner"), max_chars=80) or None
        due = _safe_text(row.get("due"), max_chars=60) or None
        key = f"{task.lower()}::{(owner or '').lower()}::{(due or '').lower()}"
        if not task or key in seen:
            continue
        output.append({"task": task, "owner": owner, "due": due})
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _safe_timeline(value: object, max_items: int = 12) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for row in _safe_list(value):
        if not isinstance(row, dict):
            continue
        time_ms = int(row.get("time_ms", 0) or 0)
        text = _safe_text(row.get("text"), max_chars=240)
        key = f"{time_ms}:{text.lower()}"
        if not text or key in seen:
            continue
        output.append({"time_ms": max(0, time_ms), "text": text})
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _sentences_from_text(text: str, max_items: int = 10, max_chars: int = 220) -> list[str]:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return []
    raw_items = [item.strip() for item in _SENTENCE_SPLIT_PATTERN.split(normalized) if item.strip()]
    if not raw_items:
        raw_items = [normalized]
    return _dedupe_texts(raw_items, max_items=max_items, max_chars=max_chars)


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        stripped = content.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(stripped)


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


def _structured_summary_payload(parsed: dict) -> dict:
    return {
        "one_liner": _safe_text(parsed.get("one_liner"), max_chars=220),
        "overview": _safe_text(parsed.get("overview"), max_chars=1000),
        "detailed_summary": _safe_text(parsed.get("detailed_summary"), max_chars=2800),
        "key_points": _safe_string_list(parsed.get("key_points"), max_items=12, max_chars=220),
        "topic_summaries": _safe_topic_summaries(parsed.get("topic_summaries"), max_items=10),
        "decisions": _safe_string_list(parsed.get("decisions"), max_items=12, max_chars=220),
        "open_questions": _safe_string_list(parsed.get("open_questions"), max_items=12, max_chars=220),
        "notable_details": _safe_string_list(parsed.get("notable_details"), max_items=14, max_chars=240),
        "action_items": _safe_action_items(parsed.get("action_items"), max_items=12),
        "keywords": _safe_string_list(parsed.get("keywords"), max_items=20, max_chars=40),
        "timeline": _safe_timeline(parsed.get("timeline"), max_items=12),
    }


def _build_summary_markdown(payload: dict) -> str:
    lines: list[str] = []

    one_liner = _safe_text(payload.get("one_liner"), max_chars=220)
    overview = _safe_text(payload.get("overview"), max_chars=1000)
    detailed_summary = _safe_text(payload.get("detailed_summary"), max_chars=2800)
    key_points = _safe_string_list(payload.get("key_points"), max_items=12, max_chars=220)
    topic_summaries = _safe_topic_summaries(payload.get("topic_summaries"), max_items=10)
    decisions = _safe_string_list(payload.get("decisions"), max_items=12, max_chars=220)
    open_questions = _safe_string_list(payload.get("open_questions"), max_items=12, max_chars=220)
    notable_details = _safe_string_list(payload.get("notable_details"), max_items=14, max_chars=240)

    if one_liner:
        lines.extend(["## 한 줄 요약", one_liner, ""])
    if overview:
        lines.extend(["## 총 요약", overview, ""])
    if detailed_summary:
        lines.extend(["## 상세 요약", detailed_summary, ""])
    if key_points:
        lines.append("## 핵심 포인트")
        lines.extend([f"- {item}" for item in key_points])
        lines.append("")
    if topic_summaries:
        lines.append("## 주제별 요약")
        for item in topic_summaries:
            lines.append(f"- **{item['topic']}**: {item['summary']}")
        lines.append("")
    if decisions:
        lines.append("## 결정 사항")
        lines.extend([f"- {item}" for item in decisions])
        lines.append("")
    if open_questions:
        lines.append("## 열린 질문")
        lines.extend([f"- {item}" for item in open_questions])
        lines.append("")
    if notable_details:
        lines.append("## 놓치기 쉬운 세부 내용")
        lines.extend([f"- {item}" for item in notable_details])
        lines.append("")

    markdown = "\n".join(lines).strip()
    return markdown or "요약을 생성하지 못했습니다."


def _has_meaningful_payload(payload: dict) -> bool:
    return any(
        [
            payload.get("one_liner"),
            payload.get("overview"),
            payload.get("detailed_summary"),
            payload.get("key_points"),
            payload.get("topic_summaries"),
            payload.get("decisions"),
            payload.get("open_questions"),
            payload.get("notable_details"),
            payload.get("action_items"),
            payload.get("keywords"),
            payload.get("timeline"),
        ]
    )


def _payload_from_text(text: str, timeline: list[dict] | None = None) -> dict:
    sentences = _sentences_from_text(text, max_items=12, max_chars=220)
    if not sentences:
        sentences = ["전사 내용을 바탕으로 요약을 구성하지 못했습니다."]
    overview = " ".join(sentences[:3])[:1000]
    detailed = " ".join(sentences[:8])[:2800]
    return {
        "one_liner": sentences[0][:220],
        "overview": overview,
        "detailed_summary": detailed,
        "key_points": sentences[:8],
        "topic_summaries": [{"topic": f"주제 {idx + 1}", "summary": item} for idx, item in enumerate(sentences[:5])],
        "decisions": [],
        "open_questions": [],
        "notable_details": sentences[3:10],
        "action_items": [],
        "keywords": [],
        "timeline": _safe_timeline(timeline or [], max_items=12),
    }


def _fallback_map_item_from_chunk(chunk: dict) -> dict:
    chunk_text = _safe_text(chunk.get("text"), max_chars=settings.summary_map_chunk_chars)
    payload = _payload_from_text(
        chunk_text,
        timeline=[{"time_ms": int(chunk.get("start_ms", 0) or 0), "text": chunk_text[:220]}],
    )
    return {
        "summary": payload["overview"],
        "detailed_summary": payload["detailed_summary"],
        "key_points": payload["key_points"],
        "topic_summaries": payload["topic_summaries"],
        "decisions": payload["decisions"],
        "open_questions": payload["open_questions"],
        "notable_details": payload["notable_details"],
        "action_items": payload["action_items"],
        "keywords": payload["keywords"],
        "timeline": payload["timeline"],
    }


def _payload_from_mapped_items(mapped: list[dict]) -> dict:
    summaries = _dedupe_texts(
        [str(item.get("summary") or item.get("detailed_summary") or "") for item in mapped],
        max_items=10,
        max_chars=260,
    )
    details = _dedupe_texts(
        [str(item.get("detailed_summary") or item.get("summary") or "") for item in mapped],
        max_items=16,
        max_chars=320,
    )
    key_points = _dedupe_texts(
        [point for item in mapped for point in _safe_string_list(item.get("key_points"), max_items=8, max_chars=220)],
        max_items=14,
        max_chars=220,
    )
    topic_summaries = _safe_topic_summaries(
        [topic for item in mapped for topic in _safe_list(item.get("topic_summaries"))],
        max_items=10,
    )
    decisions = _dedupe_texts(
        [point for item in mapped for point in _safe_string_list(item.get("decisions"), max_items=6, max_chars=220)],
        max_items=12,
        max_chars=220,
    )
    open_questions = _dedupe_texts(
        [point for item in mapped for point in _safe_string_list(item.get("open_questions"), max_items=6, max_chars=220)],
        max_items=12,
        max_chars=220,
    )
    notable_details = _dedupe_texts(
        [point for item in mapped for point in _safe_string_list(item.get("notable_details"), max_items=8, max_chars=240)],
        max_items=14,
        max_chars=240,
    )
    action_items = _safe_action_items(
        [row for item in mapped for row in _safe_list(item.get("action_items"))],
        max_items=12,
    )
    keywords = _safe_string_list(
        [word for item in mapped for word in _safe_string_list(item.get("keywords"), max_items=15, max_chars=40)],
        max_items=20,
        max_chars=40,
    )
    timeline = _safe_timeline(
        [row for item in mapped for row in _safe_list(item.get("timeline"))],
        max_items=12,
    )
    if not summaries and details:
        summaries = details[:3]
    if not details and summaries:
        details = summaries
    return {
        "one_liner": (summaries or key_points or notable_details or ["요약 결과를 정리했습니다."])[0][:220],
        "overview": " ".join((summaries or key_points)[:4])[:1000],
        "detailed_summary": " ".join((details or summaries or key_points)[:10])[:2800],
        "key_points": key_points or summaries[:8],
        "topic_summaries": topic_summaries or [{"topic": f"주제 {idx + 1}", "summary": item} for idx, item in enumerate(summaries[:5])],
        "decisions": decisions,
        "open_questions": open_questions,
        "notable_details": notable_details or details[4:12],
        "action_items": action_items,
        "keywords": keywords,
        "timeline": timeline,
    }


def _summary_result_from_parsed(parsed: dict) -> tuple[str, list[dict], list[str], list[dict]]:
    payload = _structured_summary_payload(parsed)
    if not _has_meaningful_payload(payload):
        payload = _payload_from_text("")
    summary_md = _build_summary_markdown(payload)
    return summary_md, payload["action_items"], payload["keywords"], payload["timeline"]


def _map_item_from_parsed(parsed: dict) -> dict:
    return {
        "summary": _safe_text(parsed.get("summary"), max_chars=900),
        "detailed_summary": _safe_text(parsed.get("detailed_summary"), max_chars=1400),
        "key_points": _safe_string_list(parsed.get("key_points"), max_items=8, max_chars=180),
        "topic_summaries": _safe_topic_summaries(parsed.get("topic_summaries"), max_items=6),
        "decisions": _safe_string_list(parsed.get("decisions"), max_items=6, max_chars=180),
        "open_questions": _safe_string_list(parsed.get("open_questions"), max_items=6, max_chars=180),
        "notable_details": _safe_string_list(parsed.get("notable_details"), max_items=8, max_chars=200),
        "action_items": _safe_action_items(parsed.get("action_items"), max_items=8),
        "keywords": _safe_string_list(parsed.get("keywords"), max_items=15, max_chars=40),
        "timeline": _safe_timeline(parsed.get("timeline"), max_items=8),
    }


def _compact_map_item(item: dict) -> dict:
    summary = _safe_text(item.get("summary"), max_chars=900)
    topic_summaries = _safe_topic_summaries(item.get("topic_summaries"), max_items=6)
    if not topic_summaries and summary:
        topic_summaries = [{"topic": "청크 요약", "summary": summary[:400]}]
    return {
        "summary": summary,
        "detailed_summary": _safe_text(item.get("detailed_summary"), max_chars=1400),
        "key_points": _safe_string_list(item.get("key_points"), max_items=8, max_chars=180),
        "topic_summaries": topic_summaries,
        "decisions": _safe_string_list(item.get("decisions"), max_items=6, max_chars=180),
        "open_questions": _safe_string_list(item.get("open_questions"), max_items=6, max_chars=180),
        "notable_details": _safe_string_list(item.get("notable_details"), max_items=8, max_chars=200),
        "action_items": _safe_action_items(item.get("action_items"), max_items=8),
        "keywords": _safe_string_list(item.get("keywords"), max_items=15, max_chars=40),
        "timeline": _safe_timeline(item.get("timeline"), max_items=8),
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
                logger.warning("Summary JSON parse failed. Raw content prefix: %s", content[:500])
                return {}
        except BadRequestError as exc:
            if not _is_context_limit_error(exc):
                logger.warning("Summary request failed with BadRequestError: %s", str(exc)[:500])
                return {}
            next_limit = max(1000, int(len(candidate) * 0.7))
            if next_limit >= len(candidate):
                logger.warning("Summary request hit context limit and could not be reduced further.")
                return {}
            logger.warning(
                "Summary request hit context limit. Reducing input from %s to %s characters.",
                len(candidate),
                next_limit,
            )
            candidate = _truncate_middle(candidate, next_limit)
        except Exception:
            logger.exception("Summary request failed unexpectedly.")
            return {}
    return {}


def _fallback_summary(transcript: Transcript) -> tuple[str, list[dict], list[str], list[dict], str]:
    timeline = [{"time_ms": segment["start_ms"], "text": segment["text"]} for segment in transcript.segments[:8]]
    payload = _payload_from_text(transcript.full_text[:5000], timeline=timeline)
    summary_md = _build_summary_markdown(payload)
    return summary_md, payload["action_items"], payload["keywords"], payload["timeline"], "fallback-summary-v3"


def _one_pass_summary(client, transcript_text: str) -> tuple[str, list[dict], list[str], list[dict], str]:
    prompt = (
        "You are a meeting/class note assistant.\n"
        "Preserve as much important content as possible. Do not over-compress. "
        "If there are multiple agenda items, keep them separate instead of merging them.\n"
        "Return JSON only with keys:\n"
        "one_liner, overview, detailed_summary, key_points, topic_summaries, "
        "decisions, open_questions, notable_details, action_items, keywords, timeline.\n"
        "topic_summaries must be an array of {topic, summary}. "
        "action_items must be an array of {task, owner, due}. "
        "timeline must be an array of {time_ms, text}. "
        "Use Korean for every text field."
    )
    parsed = _safe_chat_json(client, prompt, transcript_text)
    payload = _structured_summary_payload(parsed)
    if not _has_meaningful_payload(payload):
        logger.warning("One-pass summary returned empty structured payload; using extractive fallback.")
        payload = _payload_from_text(transcript_text)
        mode = "one-pass-extractive-fallback"
    else:
        mode = "one-pass"
    summary_md = _build_summary_markdown(payload)
    return summary_md, payload["action_items"], payload["keywords"], payload["timeline"], mode


def _map_reduce_summary(transcript: Transcript, client) -> tuple[str, list[dict], list[str], list[dict], str]:
    chunks = chunk_transcript_segments(
        transcript.segments,
        max_chars=settings.summary_map_chunk_chars,
        overlap_chars=min(220, max(80, settings.summary_map_chunk_chars // 8)),
    )[: settings.summary_map_max_chunks]
    if not chunks:
        return _one_pass_summary(client, transcript.full_text[:4000])
    if len(chunks) == 1:
        return _one_pass_summary(client, chunks[0]["text"])

    map_prompt = (
        "You summarize one transcript chunk from a meeting/class.\n"
        "Preserve concrete details. Better slightly verbose than overly compressed.\n"
        "Return JSON keys only: summary, detailed_summary, key_points, topic_summaries, "
        "decisions, open_questions, notable_details, action_items, keywords, timeline.\n"
        "topic_summaries: array of {topic, summary}. "
        "action_items: array of {task, owner, due}. "
        "timeline: array of {time_ms, text}. "
        "Use Korean for every text field."
    )
    mapped: list[dict] = []
    used_map_fallback = False
    for chunk in chunks:
        chunk_text = str(chunk["text"])[: settings.summary_map_chunk_chars]
        parsed = _safe_chat_json(client, map_prompt, chunk_text)
        map_item = _map_item_from_parsed(parsed)
        if not any(map_item.values()):
            logger.warning("Chunk summary returned empty payload; using chunk fallback.")
            map_item = _fallback_map_item_from_chunk(chunk)
            used_map_fallback = True
        mapped.append(map_item)

    reduce_prompt = (
        "Merge chunk summaries into a rich final summary.\n"
        "Preserve most major details from the chunks instead of compressing them into a short abstract.\n"
        "Return JSON only with keys: one_liner, overview, detailed_summary, key_points, "
        "topic_summaries, decisions, open_questions, notable_details, action_items, keywords, timeline.\n"
        "topic_summaries: array of {topic, summary}. "
        "action_items: array of {task, owner, due}. "
        "timeline: array of {time_ms, text}. "
        "Use Korean for every text field."
    )
    reduce_input = _bounded_reduce_input(mapped)
    parsed = _safe_chat_json(client, reduce_prompt, reduce_input)
    payload = _structured_summary_payload(parsed)
    if not _has_meaningful_payload(payload):
        logger.warning("Reduce summary returned empty structured payload; using merged extractive fallback.")
        payload = _payload_from_mapped_items(mapped)
        mode = "map-reduce-extractive-fallback"
    elif used_map_fallback:
        mode = "map-reduce-chunk-fallback"
    else:
        mode = "map-reduce"
    summary_md = _build_summary_markdown(payload)
    return summary_md, payload["action_items"], payload["keywords"], payload["timeline"], mode


def run_summary(db: Session, recording_id: str) -> None:
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise ValueError("Transcript not found")

    client = get_openai_client()
    if client is None:
        summary_md, action_items, keywords, timeline, model_name = _fallback_summary(transcript)
    else:
        summary_md, action_items, keywords, timeline, mode = _map_reduce_summary(transcript, client)
        model_name = f"{settings.openai_chat_model}:{mode}"

    if not summary_md or summary_md.strip() == "요약을 생성하지 못했습니다.":
        logger.warning("Summary result was still empty after generation; forcing transcript fallback.")
        summary_md, action_items, keywords, timeline, fallback_model = _fallback_summary(transcript)
        model_name = fallback_model

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
