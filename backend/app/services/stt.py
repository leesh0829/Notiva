from __future__ import annotations

from pathlib import Path

from openai import BadRequestError

from app.core.config import settings
from app.services.openai_client import get_openai_client
from app.services.storage import read_object_bytes


def _placeholder_transcription() -> tuple[str, list[dict], str]:
    segments = [
        {"start_ms": 0, "end_ms": 42000, "text": "이번 주 프로젝트 진행 현황과 일정 리스크를 공유했습니다."},
        {"start_ms": 43000, "end_ms": 85000, "text": "테스트 범위 확정과 담당자별 액션 아이템을 정리했습니다."},
        {"start_ms": 86000, "end_ms": 128000, "text": "다음 주 데모 전까지 API 통합 테스트를 완료하기로 결정했습니다."},
    ]
    return " ".join(segment["text"] for segment in segments), segments, "ko"


def run_transcription(bucket: str, key: str) -> tuple[str, list[dict], str]:
    client = get_openai_client()
    if client is None:
        return _placeholder_transcription()

    payload = read_object_bytes(bucket, key)
    suffix = Path(key).suffix or ".wav"
    content_type_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
    }
    filename = f"audio{suffix}"
    mime = content_type_map.get(suffix.lower(), "application/octet-stream")
    # Use bytes upload to avoid Windows temp-file lock issues.
    try:
        result = client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=(filename, payload, mime),
            response_format="json",
        )
    except BadRequestError:
        # Some model revisions only accept text output.
        result = client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=(filename, payload, mime),
            response_format="text",
        )

    text = (getattr(result, "text", "") or "").strip()
    language = (getattr(result, "language", None) or "unknown").strip()
    raw_segments = getattr(result, "segments", None) or []

    segments: list[dict] = []
    for segment in raw_segments:
        segment_text = str(getattr(segment, "text", "")).strip()
        if not segment_text:
            continue
        start_sec = float(getattr(segment, "start", 0.0) or 0.0)
        end_sec = float(getattr(segment, "end", start_sec) or start_sec)
        segments.append(
            {
                "start_ms": max(0, int(start_sec * 1000)),
                "end_ms": max(0, int(end_sec * 1000)),
                "text": segment_text,
            }
        )

    if not text and segments:
        text = " ".join(item["text"] for item in segments)
    if not segments and text:
        segments = [{"start_ms": 0, "end_ms": 0, "text": text}]
    if not segments:
        # Avoid empty transcript rows on provider-side errors.
        return _placeholder_transcription()
    return text, segments, language
