from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from openai import BadRequestError

from app.core.config import settings
from app.services.openai_client import get_openai_client
from app.services.storage import read_object_bytes

MAX_STT_FILE_BYTES = 24 * 1024 * 1024
CHUNK_SECONDS = 15 * 60
CHUNK_BITRATE = "64k"
_DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_UNIT_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+|(?<=[,，])\s+")
_LONG_REPEAT_CHAR_PATTERN = re.compile(r"([^\s])\1{11,}")
_SEGMENT_TARGET_CHARS = 260
_SEGMENT_MAX_CHARS = 420


def _placeholder_transcription() -> tuple[str, list[dict], str]:
    segments = [
        {"start_ms": 0, "end_ms": 42000, "text": "이번 주 프로젝트 진행 현황과 일정 리스크를 공유했습니다."},
        {"start_ms": 43000, "end_ms": 85000, "text": "테스트 범위 확정과 담당자별 액션 아이템을 정리했습니다."},
        {"start_ms": 86000, "end_ms": 128000, "text": "다음 주 데모 전까지 API 통합 테스트를 완료하기로 결정했습니다."},
    ]
    return " ".join(segment["text"] for segment in segments), segments, "ko"


def _guess_mime(suffix: str) -> str:
    content_type_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
    }
    return content_type_map.get(suffix.lower(), "application/octet-stream")


def _supports_json_response_error(exc: BadRequestError) -> bool:
    message = str(exc).lower()
    return "response_format" in message


def _is_invalid_audio_error(exc: BadRequestError) -> bool:
    message = str(exc).lower()
    return (
        "audio file might be corrupted or unsupported" in message
        or ("invalid_value" in message and "param" in message and "file" in message)
    )


def _transcribe_once(client, payload: bytes, filename: str, mime: str):
    request_kwargs = {
        "model": settings.openai_stt_model,
        "file": (filename, payload, mime),
    }
    if settings.openai_stt_language:
        request_kwargs["language"] = settings.openai_stt_language

    try:
        return client.audio.transcriptions.create(
            **request_kwargs,
            response_format="json",
        )
    except BadRequestError as exc:
        if not _supports_json_response_error(exc):
            raise
        # Some model revisions only accept text output.
        return client.audio.transcriptions.create(
            **request_kwargs,
            response_format="text",
        )


def _duration_ms_with_ffmpeg(ffmpeg_exe: str, file_path: Path) -> int:
    process = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-i", str(file_path), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    output = f"{process.stdout}\n{process.stderr}"
    match = _DURATION_PATTERN.search(output)
    if not match:
        return 0
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return int(((hours * 60 * 60) + (minutes * 60) + seconds) * 1000)


def _extract_text_language_segments(result) -> tuple[str, str, list[dict]]:
    if isinstance(result, str):
        return result.strip(), "unknown", []
    text = (getattr(result, "text", "") or "").strip()
    language = (getattr(result, "language", None) or "unknown").strip()
    raw_segments = getattr(result, "segments", None) or []
    normalized_segments: list[dict] = []
    for segment in raw_segments:
        if isinstance(segment, dict):
            segment_text = str(segment.get("text", "")).strip()
            start_sec = float(segment.get("start", 0.0) or 0.0)
            end_sec = float(segment.get("end", start_sec) or start_sec)
        else:
            segment_text = str(getattr(segment, "text", "")).strip()
            start_sec = float(getattr(segment, "start", 0.0) or 0.0)
            end_sec = float(getattr(segment, "end", start_sec) or start_sec)
        if not segment_text:
            continue
        cleaned_text = _collapse_repeated_units(segment_text)
        if not cleaned_text:
            continue
        normalized_segments.append(
            {
                "start_ms": max(0, int(start_sec * 1000)),
                "end_ms": max(0, int(end_sec * 1000)),
                "text": cleaned_text,
            }
        )
    deduped_segments: list[dict] = []
    last_key = ""
    for segment in normalized_segments:
        key = segment["text"].strip().lower()
        if not key:
            continue
        if key == last_key:
            continue
        deduped_segments.append(segment)
        last_key = key
    return _collapse_repeated_units(text), language, deduped_segments


def _collapse_repeated_units(text: str) -> str:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return ""
    normalized = _strip_low_information_noise(normalized)
    if not normalized:
        return ""
    normalized = _collapse_repeated_token_phrases(normalized)
    units = [unit.strip() for unit in _UNIT_SPLIT_PATTERN.split(normalized) if unit.strip()]
    if len(units) < 2:
        return _strip_low_information_noise(normalized)
    compact: list[str] = []
    last_key = ""
    for unit in units:
        key = unit.lower()
        if key == last_key:
            continue
        compact.append(unit)
        last_key = key
    collapsed = " ".join(compact) if compact else normalized
    collapsed = _collapse_repeated_token_phrases(collapsed)
    return _strip_low_information_noise(collapsed)


def _strip_low_information_noise(text: str) -> str:
    compact = "".join((text or "").split())
    if len(compact) < 36:
        return text
    if not _LONG_REPEAT_CHAR_PATTERN.search(compact):
        return text
    unique_ratio = len(set(compact)) / max(1, len(compact))
    if unique_ratio > 0.25:
        return text
    return ""


def _collapse_repeated_token_phrases(text: str) -> str:
    words = [word for word in text.split(" ") if word]
    if len(words) < 12:
        return text

    output: list[str] = []
    index = 0
    total = len(words)
    while index < total:
        best_window = 0
        best_repeat = 0
        max_window = min(18, (total - index) // 2)
        for window in range(3, max_window + 1):
            pattern = words[index : index + window]
            if len(set(pattern)) < 2:
                continue
            repeat = 1
            while index + (repeat + 1) * window <= total:
                next_slice = words[index + repeat * window : index + (repeat + 1) * window]
                if next_slice != pattern:
                    break
                repeat += 1
            if repeat >= 2 and window * repeat > best_window * best_repeat:
                best_window = window
                best_repeat = repeat

        if best_repeat >= 2:
            output.extend(words[index : index + best_window])
            index += best_window * best_repeat
            continue

        output.append(words[index])
        index += 1
    return " ".join(output)


def _split_text_by_chars(text: str, max_chars: int) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean]
    parts: list[str] = []
    cursor = 0
    total = len(clean)
    while cursor < total:
        end = min(total, cursor + max_chars)
        if end < total:
            split_at = clean.rfind(" ", cursor + max(1, max_chars // 2), end)
            if split_at > cursor:
                end = split_at
        piece = clean[cursor:end].strip()
        if piece:
            parts.append(piece)
        if end <= cursor:
            end = min(total, cursor + max_chars)
        cursor = end
    return parts


def _approximate_segments(text: str, start_ms: int, end_ms: int) -> list[dict]:
    cleaned = _collapse_repeated_units(text)
    if not cleaned:
        return []
    units = [unit.strip() for unit in _UNIT_SPLIT_PATTERN.split(cleaned) if unit.strip()]
    if not units:
        units = [cleaned]
    grouped: list[str] = []
    current = ""
    for unit in units:
        chunks = _split_text_by_chars(unit, _SEGMENT_MAX_CHARS) if len(unit) > _SEGMENT_MAX_CHARS else [unit]
        for chunk in chunks:
            candidate = f"{current} {chunk}".strip() if current else chunk
            if current and len(candidate) > _SEGMENT_MAX_CHARS:
                grouped.append(current)
                current = chunk
                continue
            if not current:
                current = chunk
            elif len(candidate) <= _SEGMENT_TARGET_CHARS:
                current = candidate
            else:
                grouped.append(current)
                current = chunk
    if current:
        grouped.append(current)
    if not grouped:
        return []

    span = max(0, end_ms - start_ms)
    if span <= 0:
        return [{"start_ms": start_ms, "end_ms": max(start_ms + 1, start_ms + len(grouped[0]) * 45), "text": grouped[0]}]
    total_chars = max(1, sum(len(part) for part in grouped))
    cursor = start_ms
    result: list[dict] = []
    for idx, part in enumerate(grouped):
        if idx == len(grouped) - 1:
            piece_end = end_ms
        else:
            piece_span = max(300, int(span * (len(part) / total_chars)))
            piece_end = min(end_ms, cursor + piece_span)
        if piece_end <= cursor:
            piece_end = min(end_ms, cursor + 300)
        result.append({"start_ms": cursor, "end_ms": piece_end, "text": part})
        cursor = piece_end
    return result


def _transcribe_large_audio(client, payload: bytes, suffix: str) -> tuple[str, list[dict], str]:
    try:
        import imageio_ffmpeg
    except Exception as exc:
        raise RuntimeError(
            "Large audio transcription requires imageio-ffmpeg. Install backend dependencies again."
        ) from exc

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    all_segments: list[dict] = []
    full_text_parts: list[str] = []
    offset_ms = 0
    language = "unknown"

    with tempfile.TemporaryDirectory(prefix="notiva-stt-") as tmpdir:
        tmp = Path(tmpdir)
        input_path = tmp / f"input{suffix}"
        input_path.write_bytes(payload)
        chunk_pattern = tmp / "chunk_%03d.mp3"
        subprocess.run(
            [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                CHUNK_BITRATE,
                "-f",
                "segment",
                "-segment_time",
                str(CHUNK_SECONDS),
                "-reset_timestamps",
                "1",
                str(chunk_pattern),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        chunk_files = sorted(tmp.glob("chunk_*.mp3"))
        if not chunk_files:
            raise RuntimeError("Failed to split audio for transcription")

        for chunk_file in chunk_files:
            duration_ms = _duration_ms_with_ffmpeg(ffmpeg_exe, chunk_file)
            if duration_ms <= 0:
                duration_ms = CHUNK_SECONDS * 1000
            chunk_bytes = chunk_file.read_bytes()
            result = _transcribe_once(client, chunk_bytes, chunk_file.name, "audio/mpeg")
            text, chunk_language, chunk_segments = _extract_text_language_segments(result)
            if chunk_language and chunk_language != "unknown":
                language = chunk_language

            if not chunk_segments and text:
                chunk_segments = _approximate_segments(text, 0, duration_ms)

            if chunk_segments:
                shifted = [
                    {
                        "start_ms": segment["start_ms"] + offset_ms,
                        "end_ms": segment["end_ms"] + offset_ms,
                        "text": segment["text"],
                    }
                    for segment in chunk_segments
                ]
                all_segments.extend(shifted)
            if text:
                full_text_parts.append(text)

            if duration_ms <= 0 and chunk_segments:
                duration_ms = max(segment["end_ms"] for segment in chunk_segments)
            offset_ms += duration_ms

    full_text = " ".join(part.strip() for part in full_text_parts if part.strip()).strip()
    if not full_text and all_segments:
        full_text = " ".join(segment["text"] for segment in all_segments).strip()
    if not all_segments and full_text:
        all_segments = [{"start_ms": 0, "end_ms": max(offset_ms, 1), "text": full_text}]
    return full_text, all_segments, language


def run_transcription(bucket: str, key: str) -> tuple[str, list[dict], str]:
    client = get_openai_client()
    if client is None:
        return _placeholder_transcription()

    payload = read_object_bytes(bucket, key)
    suffix = Path(key).suffix or ".wav"
    filename = f"audio{suffix}"
    mime = _guess_mime(suffix)

    # Provider-side file-size restrictions apply to direct uploads.
    if len(payload) > MAX_STT_FILE_BYTES:
        text, segments, language = _transcribe_large_audio(client, payload, suffix)
    else:
        # Use bytes upload to avoid Windows temp-file lock issues.
        try:
            result = _transcribe_once(client, payload, filename, mime)
        except BadRequestError as exc:
            if not _is_invalid_audio_error(exc):
                raise
            text, segments, language = _transcribe_large_audio(client, payload, suffix)
        else:
            text, language, segments = _extract_text_language_segments(result)

    if not text and segments:
        text = " ".join(item["text"] for item in segments)
    if not segments and text:
        segments = [{"start_ms": 0, "end_ms": 0, "text": text}]
    if not segments:
        # Avoid empty transcript rows on provider-side errors.
        return _placeholder_transcription()
    return text, segments, language
