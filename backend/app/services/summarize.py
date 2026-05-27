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

logger = logging.getLogger(__name__)

REDUCE_INPUT_MAX_CHARS = 180_000
MAP_CHUNK_SUMMARY_MAX_CHARS = 12_000
FALLBACK_TRANSCRIPT_MAX_CHARS = 30_000

_LIST_BULLET_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            line = _coerce_text(item).strip()
            if not line:
                continue
            if not _LIST_BULLET_PATTERN.match(line):
                line = f"- {line}"
            parts.append(line)
        return "\n".join(parts)
    if isinstance(value, dict):
        for key in ("text", "summary", "content", "value", "body"):
            if key in value:
                return _coerce_text(value.get(key))
        return ""
    return str(value)


def _clean_markdown(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _normalize_keywords(value: object, max_items: int = 20) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return output
    for raw in value:
        if isinstance(raw, dict):
            raw = raw.get("keyword") or raw.get("text") or raw.get("name") or ""
        text = str(raw or "").strip().strip("#").strip()
        if not text:
            continue
        text = text[:40]
        key = text.lower()
        if key in seen:
            continue
        output.append(text)
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _normalize_action_items(value: object, max_items: int = 20) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return output
    for raw in value:
        if not isinstance(raw, dict):
            if isinstance(raw, str) and raw.strip():
                task = raw.strip()[:240]
                key = task.lower()
                if key in seen:
                    continue
                output.append({"task": task, "owner": None, "due": None})
                seen.add(key)
            continue
        task = str(raw.get("task") or raw.get("action") or raw.get("item") or "").strip()
        if not task:
            continue
        task = task[:240]
        owner_raw = raw.get("owner") or raw.get("assignee") or raw.get("who")
        due_raw = raw.get("due") or raw.get("deadline") or raw.get("when")
        owner = str(owner_raw).strip()[:80] if owner_raw else None
        due = str(due_raw).strip()[:80] if due_raw else None
        key = f"{task.lower()}::{(owner or '').lower()}::{(due or '').lower()}"
        if key in seen:
            continue
        output.append({"task": task, "owner": owner or None, "due": due or None})
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _normalize_timeline(value: object, max_items: int = 24) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return output
    for raw in value:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or raw.get("summary") or "").strip()
        if not text:
            continue
        try:
            time_ms = int(raw.get("time_ms", 0) or 0)
        except (TypeError, ValueError):
            time_ms = 0
        text = text[:240]
        key = f"{time_ms}::{text.lower()}"
        if key in seen:
            continue
        output.append({"time_ms": max(0, time_ms), "text": text})
        seen.add(key)
        if len(output) >= max_items:
            break
    return output


def _parse_json(content: str) -> dict:
    raw = (content or "").strip()
    if not raw:
        return {}
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        stripped = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            result = json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning("Summary JSON parse failed. Raw prefix: %s", raw[:300])
            return {}
    return result if isinstance(result, dict) else {}


def _is_context_limit_error(exc: BadRequestError) -> bool:
    message = str(exc).lower()
    return "maximum context length" in message or "please reduce your prompt" in message


def _truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars < 80:
        return text[:max_chars]
    head = int(max_chars * 0.6)
    tail = max_chars - head - 20
    return f"{text[:head]}\n\n...[중략]...\n\n{text[-tail:]}"


def _safe_chat_json(client, system_prompt: str, user_text: str) -> dict:
    candidate = user_text
    for _ in range(5):
        try:
            completion = client.chat.completions.create(
                model=settings.openai_chat_model,
                response_format={"type": "json_object"},
                temperature=0.3,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": candidate},
                ],
            )
            content = completion.choices[0].message.content or "{}"
            return _parse_json(content)
        except BadRequestError as exc:
            if not _is_context_limit_error(exc):
                logger.warning("Summary request failed: %s", str(exc)[:300])
                return {}
            next_limit = max(2000, int(len(candidate) * 0.7))
            if next_limit >= len(candidate):
                logger.warning("Summary input still too large after reduction.")
                return {}
            logger.warning("Summary hit context limit. Reducing %s -> %s chars.", len(candidate), next_limit)
            candidate = _truncate_middle(candidate, next_limit)
        except Exception:
            logger.exception("Summary request crashed unexpectedly.")
            return {}
    return {}


SUMMARY_SYSTEM_PROMPT = """너는 회의/강의 녹취록을 정리하는 한국어 노트 작성자다.

목표: 사용자가 "이거 그냥 ChatGPT한테 요약해달라고 한 것보다 깔끔하다"고 느낄 만큼,
계층적이고 가독성 좋은 마크다운 노트를 한 덩어리로 만든다.

[summary_md 작성 규칙 — 절대 어기지 마라]
1. 출력은 자유 형식 마크다운 한 덩어리. 절대 짧게 압축하지 마라. 원본의 구체적 사실을 보존해라.
2. 가장 먼저 `## 한 줄 요약` 섹션. 한 문장(공백 포함 80~160자) 으로 회의/강의의 주된 줄기를 적어라.
3. 그 다음 `## ` 헤더로 큰 주제를 3~8개 만들어라. 큰 주제 제목은 구체적이어야 한다.
   - 좋은 예: `## 6월 감리 대응 일정`, `## AAS + OPC UA 개발 현황`, `## AMR / AMS 연동 방향`
   - 나쁜 예 (절대 쓰지 마라): `## 총 요약`, `## 핵심 포인트`, `## 주제별 요약`, `## 내용 정리`
4. 각 `## ` 섹션 안에서 필요하면 `### ` 하위 제목으로 더 쪼개라.
5. 본문은 글머리표(`- `) 위주로. 한 글머리표는 1~3문장. 길게 늘어진 산문 문단은 금지.
6. 화자/발화 행위 메타 묘사 금지. ("이번 회의에서는 ... 논의했다", "교수님은 ... 강조했다" 같은 말 쓰지 마라.)
   대신 실제로 결정/설명/계획된 내용 그 자체를 적어라.
7. 결정 사항이 있으면 `## 결정 / 합의` 같은 섹션을 따로 만들어 적어라. (단, 같은 내용을 다른 섹션과 중복해서 쓰지 마라.)
8. 후속 질문/미해결 사항이 있으면 `## 남은 질문` 같은 섹션을 만들어라.
9. 어휘는 회의에서 실제 사용된 용어 그대로(예: AAS, OPC UA, AMR, ICC, WBS, PMO, MES, PLC).

[추가 필드]
- action_items: 후속으로 누가 무엇을 언제까지 할지. `{"task","owner","due"}`. 없으면 빈 배열.
  같은 내용을 summary_md 본문에 또 적어도 되지만, action_items 자체는 비워두지 마라(있다면).
- keywords: 단어/짧은 구. 6~15개. 회의 핵심 용어.
- timeline: 녹취록에 명확한 시간 흐름이 있을 때만 작성. `{"time_ms","text"}`. 없거나 모르면 빈 배열.

[출력 형식]
반드시 JSON 객체로만. 네 가지 키:
{
  "summary_md": "<위 규칙대로 작성한 한국어 마크다운 한 덩어리>",
  "action_items": [{"task":"...","owner":"...","due":"..."}],
  "keywords": ["..."],
  "timeline": [{"time_ms": 0, "text": "..."}]
}
"""

MAP_SYSTEM_PROMPT = """너는 긴 회의/강의 녹취록의 한 청크를 요약하는 한국어 작성자다.

[summary_md 규칙]
- 이 청크에서 실제로 다뤄진 내용만, 위계적 마크다운으로. `## ` 큰 주제 1~3개 + 각 주제 아래 `- ` 글머리표.
- `## ` 제목은 청크 내용에서 가져온 구체적 표현이어야 한다. `## 내용 정리` 같은 placeholder 금지.
- 글머리표는 1~3문장. 산문 문단 금지.
- 화자/발화 행위 묘사 금지. 실제 내용만.
- 어휘는 청크에서 사용된 용어 그대로.

[추가 필드]
- action_items: 이 청크에서 명시된 후속 작업만. 없으면 빈 배열.
- keywords: 이 청크의 핵심 용어 5~10개.

[출력 JSON]
{
  "summary_md": "<청크의 한국어 마크다운 요약>",
  "action_items": [{"task":"...","owner":"...","due":"..."}],
  "keywords": ["..."]
}
"""

REDUCE_SYSTEM_PROMPT = """너는 청크 단위로 만들어진 부분 요약들을 하나의 최종 노트로 통합하는 한국어 작성자다.

받는 입력은 청크별 부분 요약(`chunks: [{summary_md, action_items, keywords}]`)이다.
이를 합쳐 사용자가 ChatGPT 출력처럼 깔끔하다고 느낄, 계층적이고 풍부한 한국어 마크다운 노트를 만든다.

[summary_md 작성 규칙 — 절대 어기지 마라]
1. 자유 형식 마크다운 한 덩어리. 압축 최소화. 청크들의 구체적 사실을 최대한 보존해라.
2. 시작은 `## 한 줄 요약` (한 문장, 공백 포함 80~160자).
3. 다음으로 `## ` 큰 주제를 3~8개. 청크들에서 같은 주제는 통합해라.
   - 좋은 예: `## 6월 감리 대응 일정`, `## AAS + OPC UA 개발 현황`
   - 나쁜 예 (금지): `## 총 요약`, `## 핵심 포인트`, `## 주제별 요약`, `## 내용 정리`
4. 필요시 `### ` 로 더 쪼개라. 글머리표(`- `)는 1~3문장.
5. 산문 문단 금지. 화자/발화 행위 묘사 금지.
6. 결정 사항은 `## 결정 / 합의`, 미해결은 `## 남은 질문` 같은 섹션으로 (있을 때만).
7. 어휘는 청크들에서 사용된 용어 그대로.

[추가 필드]
- action_items: 청크들에서 모은 후속 작업 합쳐서 중복 제거.
- keywords: 6~15개로 통합.
- timeline: 청크들에 시간 흐름 명시가 있다면 통합. 없으면 빈 배열.

[출력 JSON]
{
  "summary_md": "...",
  "action_items": [{"task":"...","owner":"...","due":"..."}],
  "keywords": ["..."],
  "timeline": [{"time_ms":0,"text":"..."}]
}
"""


def _result_from_parsed(parsed: dict) -> tuple[str, list[dict], list[str], list[dict]]:
    summary_md = _clean_markdown(_coerce_text(parsed.get("summary_md")))
    action_items = _normalize_action_items(parsed.get("action_items"))
    keywords = _normalize_keywords(parsed.get("keywords"))
    timeline = _normalize_timeline(parsed.get("timeline"))
    return summary_md, action_items, keywords, timeline


def _map_item_from_parsed(parsed: dict) -> dict:
    summary_md = _clean_markdown(_coerce_text(parsed.get("summary_md")))
    if len(summary_md) > MAP_CHUNK_SUMMARY_MAX_CHARS:
        summary_md = summary_md[:MAP_CHUNK_SUMMARY_MAX_CHARS]
    return {
        "summary_md": summary_md,
        "action_items": _normalize_action_items(parsed.get("action_items"), max_items=10),
        "keywords": _normalize_keywords(parsed.get("keywords"), max_items=10),
    }


def _fallback_map_item_from_chunk(chunk: dict) -> dict:
    chunk_text = str(chunk.get("text") or "").strip()
    if not chunk_text:
        return {"summary_md": "", "action_items": [], "keywords": []}
    body = chunk_text[:1500]
    summary_md = f"## 청크 발췌\n{body}"
    return {"summary_md": summary_md, "action_items": [], "keywords": []}


def _build_reduce_input(mapped: list[dict]) -> str:
    chunks: list[dict] = []
    payload_str = ""
    for item in mapped:
        if not item.get("summary_md") and not item.get("action_items") and not item.get("keywords"):
            continue
        candidate = chunks + [item]
        payload_str = json.dumps({"chunks": candidate}, ensure_ascii=False)
        if len(payload_str) > REDUCE_INPUT_MAX_CHARS and chunks:
            break
        chunks = candidate
    if not chunks:
        chunks = [item for item in mapped[:1] if item.get("summary_md")]
        payload_str = json.dumps({"chunks": chunks}, ensure_ascii=False)
    return payload_str or json.dumps({"chunks": []}, ensure_ascii=False)


def _fallback_summary(transcript: Transcript) -> tuple[str, list[dict], list[str], list[dict], str]:
    body = (transcript.full_text or "").strip()[:FALLBACK_TRANSCRIPT_MAX_CHARS]
    if not body:
        summary_md = "## 한 줄 요약\n- 요약을 생성하지 못했습니다.\n\n## 본문\n- 전사 결과가 비어 있습니다."
    else:
        summary_md = (
            "## 한 줄 요약\n"
            "- 요약 모델을 호출할 수 없어 전사 발췌만 제공합니다.\n\n"
            "## 전사 발췌\n"
            f"{body}"
        )
    timeline = _normalize_timeline(
        [{"time_ms": int(seg.get("start_ms", 0) or 0), "text": str(seg.get("text") or "")} for seg in (transcript.segments or [])[:12]]
    )
    return summary_md, [], [], timeline, "fallback-summary-v4"


def _one_pass_summary(client, transcript_text: str) -> tuple[str, list[dict], list[str], list[dict], str]:
    parsed = _safe_chat_json(client, SUMMARY_SYSTEM_PROMPT, transcript_text)
    summary_md, action_items, keywords, timeline = _result_from_parsed(parsed)
    mode = "one-pass" if summary_md else "one-pass-empty"
    return summary_md, action_items, keywords, timeline, mode


def _map_reduce_summary(transcript: Transcript, client) -> tuple[str, list[dict], list[str], list[dict], str]:
    chunks = chunk_transcript_segments(
        transcript.segments,
        max_chars=settings.summary_map_chunk_chars,
        overlap_chars=min(220, max(80, settings.summary_map_chunk_chars // 8)),
    )[: settings.summary_map_max_chunks]
    if not chunks:
        return _one_pass_summary(client, (transcript.full_text or "")[:20000])
    if len(chunks) == 1:
        return _one_pass_summary(client, chunks[0]["text"])

    mapped: list[dict] = []
    used_map_fallback = False
    for chunk in chunks:
        chunk_text = str(chunk.get("text") or "")[: settings.summary_map_chunk_chars]
        parsed = _safe_chat_json(client, MAP_SYSTEM_PROMPT, chunk_text)
        item = _map_item_from_parsed(parsed)
        if not item.get("summary_md"):
            item = _fallback_map_item_from_chunk(chunk)
            used_map_fallback = True
        mapped.append(item)

    reduce_input = _build_reduce_input(mapped)
    parsed = _safe_chat_json(client, REDUCE_SYSTEM_PROMPT, reduce_input)
    summary_md, action_items, keywords, timeline = _result_from_parsed(parsed)

    if not summary_md:
        logger.warning("Reduce step returned empty markdown; concatenating chunk summaries.")
        joined = "\n\n".join(item["summary_md"] for item in mapped if item.get("summary_md"))
        summary_md = _clean_markdown(joined) or "## 한 줄 요약\n- 요약을 생성하지 못했습니다."
        merged_actions: list[dict] = []
        merged_keywords: list[str] = []
        for item in mapped:
            merged_actions.extend(item.get("action_items") or [])
            merged_keywords.extend(item.get("keywords") or [])
        action_items = _normalize_action_items(merged_actions)
        keywords = _normalize_keywords(merged_keywords)
        timeline = []
        mode = "map-reduce-concat-fallback"
    elif used_map_fallback:
        mode = "map-reduce-chunk-fallback"
    else:
        mode = "map-reduce"

    return summary_md, action_items, keywords, timeline, mode


def run_summary(db: Session, recording_id: str) -> None:
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise ValueError("Transcript not found")

    client = get_openai_client()
    if client is None:
        summary_md, action_items, keywords, timeline, model_name = _fallback_summary(transcript)
    else:
        summary_md, action_items, keywords, timeline, mode = _map_reduce_summary(transcript, client)
        if not summary_md:
            logger.warning("Summary generation returned empty markdown; using transcript fallback.")
            summary_md, action_items, keywords, timeline, fallback_model = _fallback_summary(transcript)
            model_name = fallback_model
        else:
            model_name = f"{settings.openai_chat_model}:{mode}"

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
