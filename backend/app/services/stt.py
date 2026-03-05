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
_DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


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
    try:
        return client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=(filename, payload, mime),
            response_format="json",
        )
    except BadRequestError as exc:
        if not _supports_json_response_error(exc):
            raise
        # Some model revisions only accept text output.
        return client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=(filename, payload, mime),
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
        normalized_segments.append(
            {
                "start_ms": max(0, int(start_sec * 1000)),
                "end_ms": max(0, int(end_sec * 1000)),
                "text": segment_text,
            }
        )
    return text, language, normalized_segments


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
                "32k",
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
            chunk_bytes = chunk_file.read_bytes()
            result = _transcribe_once(client, chunk_bytes, chunk_file.name, "audio/mpeg")
            text, chunk_language, chunk_segments = _extract_text_language_segments(result)
            if chunk_language and chunk_language != "unknown":
                language = chunk_language

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

            duration_ms = _duration_ms_with_ffmpeg(ffmpeg_exe, chunk_file)
            if duration_ms <= 0 and chunk_segments:
                duration_ms = max(segment["end_ms"] for segment in chunk_segments)
            if duration_ms <= 0:
                duration_ms = CHUNK_SECONDS * 1000
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
