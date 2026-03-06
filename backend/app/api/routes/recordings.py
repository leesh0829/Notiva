from __future__ import annotations

import io
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.config import settings
from app.db.models import QAMessage, Recording, Summary, Transcript, TranscriptChunk
from app.db.session import get_db
from app.schemas.qa import QAHistoryResponse, QARequest, QAResponse, QATurnOut
from app.schemas.recording import (
    FolderItemOut,
    FolderListOut,
    RecordingDetailOut,
    RecordingFavoriteUpdateRequest,
    RecordingFolderUpdateRequest,
    RecordingListOut,
    RecordingNoteUpdateRequest,
    RecordingOut,
    RecordingUpdateRequest,
    RecordingUsageItemOut,
    RecordingUsageOut,
    SummaryOut,
    TranscriptOut,
    TranscriptSegmentsUpdateRequest,
)
from app.services.rag import answer_question
from app.services.storage import delete_object, read_object_bytes, upload_to_s3
from app.tasks.jobs import enqueue_pipeline

router = APIRouter()
_UNIT_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+|(?<=[,，])\s+")
_SEGMENT_TARGET_CHARS = 260
_SEGMENT_MAX_CHARS = 420


def _estimate_tokens(text: str) -> int:
    clean = text.strip()
    if not clean:
        return 0
    return max(1, len(clean) // 4)


def _recording_label(recording: Recording) -> str:
    title = (recording.title or "").strip()
    return title or recording.id


def _get_owned_recording(db: Session, recording_id: str, user_id: str) -> Recording:
    recording = db.query(Recording).filter(Recording.id == recording_id, Recording.user_id == user_id).first()
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return recording


def _hard_delete_recording(db: Session, recording: Recording) -> None:
    db.query(QAMessage).filter(QAMessage.recording_id == recording.id).delete()
    db.query(TranscriptChunk).filter(TranscriptChunk.recording_id == recording.id).delete()
    db.query(Summary).filter(Summary.recording_id == recording.id).delete()
    db.query(Transcript).filter(Transcript.recording_id == recording.id).delete()
    try:
        delete_object(recording.s3_bucket, recording.s3_key)
    except Exception:
        pass
    db.delete(recording)


def _purge_expired_trash(db: Session, user_id: str) -> None:
    threshold = datetime.now(timezone.utc) - timedelta(days=settings.trash_retention_days)
    expired = (
        db.query(Recording)
        .filter(
            Recording.user_id == user_id,
            Recording.deleted_at.is_not(None),
            Recording.deleted_at < threshold,
        )
        .all()
    )
    if not expired:
        return
    for recording in expired:
        _hard_delete_recording(db, recording)
    db.commit()


def _coerce_segment(segment: dict, idx: int) -> dict:
    start_ms = int(segment.get("start_ms", 0) or 0)
    end_ms = int(segment.get("end_ms", start_ms) or start_ms)
    text = _collapse_repeated_units(str(segment.get("text", "")).strip())
    speaker = segment.get("speaker")
    if speaker is not None:
        speaker = str(speaker).strip() or None
    if not speaker:
        speaker = f"화자 {(idx % 2) + 1}"
    return {"start_ms": start_ms, "end_ms": end_ms, "text": text, "speaker": speaker}


def _collapse_repeated_units(text: str) -> str:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return ""
    normalized = _collapse_repeated_token_phrases(normalized)
    units = [unit.strip() for unit in _UNIT_SPLIT_PATTERN.split(normalized) if unit.strip()]
    if len(units) < 2:
        return normalized
    compact: list[str] = []
    last_key = ""
    for unit in units:
        key = unit.lower()
        if key == last_key:
            continue
        compact.append(unit)
        last_key = key
    collapsed = " ".join(compact) if compact else normalized
    return _collapse_repeated_token_phrases(collapsed)


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


def _split_segment_for_readability(segment: dict) -> list[dict]:
    text = str(segment.get("text", "")).strip()
    if not text:
        return []

    units = [unit.strip() for unit in _UNIT_SPLIT_PATTERN.split(text) if unit.strip()]
    if not units:
        units = [text]

    grouped: list[str] = []
    current = ""
    for unit in units:
        if len(unit) > _SEGMENT_MAX_CHARS:
            chunks = _split_text_by_chars(unit, _SEGMENT_MAX_CHARS)
        else:
            chunks = [unit]
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

    if len(grouped) <= 1:
        return [segment]

    start_ms = int(segment.get("start_ms", 0) or 0)
    end_ms = int(segment.get("end_ms", start_ms) or start_ms)
    span_ms = max(0, end_ms - start_ms)
    speaker = segment.get("speaker")

    result: list[dict] = []
    if span_ms <= 0:
        cursor = start_ms
        for part in grouped:
            piece_span = max(1200, len(part) * 45)
            result.append({"start_ms": cursor, "end_ms": cursor + piece_span, "text": part, "speaker": speaker})
            cursor += piece_span
        return result

    total_chars = max(1, sum(len(part) for part in grouped))
    cursor = start_ms
    for idx, part in enumerate(grouped):
        if idx == len(grouped) - 1:
            piece_end = end_ms
        else:
            piece_span = max(300, int(span_ms * (len(part) / total_chars)))
            piece_end = min(end_ms, cursor + piece_span)
        if piece_end <= cursor:
            piece_end = min(end_ms, cursor + 300)
        result.append({"start_ms": cursor, "end_ms": piece_end, "text": part, "speaker": speaker})
        cursor = piece_end
    return result


def _normalized_segments(segments: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    last_key = ""
    for segment in segments:
        coerced = _coerce_segment(segment, len(normalized))
        for expanded in _split_segment_for_readability(coerced):
            key = expanded["text"].strip().lower()
            if not key:
                continue
            if key == last_key:
                continue
            normalized.append(expanded)
            last_key = key
    return normalized


@router.get("/folders", response_model=FolderListOut)
def list_folders(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> FolderListOut:
    _purge_expired_trash(db, user_id)
    rows = (
        db.query(Recording.folder_name, func.count(Recording.id))
        .filter(
            Recording.user_id == user_id,
            Recording.deleted_at.is_(None),
            Recording.folder_name.is_not(None),
            Recording.folder_name != "",
        )
        .group_by(Recording.folder_name)
        .order_by(Recording.folder_name.asc())
        .all()
    )
    return FolderListOut(items=[FolderItemOut(name=str(name), count=int(count)) for name, count in rows])


@router.get("/usage", response_model=RecordingUsageOut)
def get_usage(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingUsageOut:
    _purge_expired_trash(db, user_id)
    recordings = (
        db.query(Recording)
        .filter(Recording.user_id == user_id, Recording.deleted_at.is_(None))
        .order_by(Recording.created_at.desc())
        .all()
    )
    items: list[RecordingUsageItemOut] = []
    for recording in recordings:
        transcript = db.query(Transcript).filter(Transcript.recording_id == recording.id).first()
        summary = db.query(Summary).filter(Summary.recording_id == recording.id).first()
        chunks = db.query(TranscriptChunk).filter(TranscriptChunk.recording_id == recording.id).all()
        qa_rows = (
            db.query(QAMessage)
            .filter(QAMessage.recording_id == recording.id, QAMessage.user_id == user_id)
            .all()
        )

        stt_tokens = _estimate_tokens(transcript.full_text) if transcript else 0
        summary_blob = ""
        if summary:
            summary_blob = "\n".join(
                [
                    summary.summary_md or "",
                    json.dumps(summary.action_items or [], ensure_ascii=False),
                    json.dumps(summary.keywords or [], ensure_ascii=False),
                    json.dumps(summary.timeline or [], ensure_ascii=False),
                ]
            )
        summary_tokens = _estimate_tokens(summary_blob)
        embedding_tokens = sum(int(chunk.token_count or _estimate_tokens(chunk.content)) for chunk in chunks)
        qa_input_tokens = 0
        qa_output_tokens = 0
        for row in qa_rows:
            citations_text = " ".join(str(citation.get("text", "")) for citation in (row.citations or []))
            qa_input_tokens += _estimate_tokens(row.question) + _estimate_tokens(citations_text)
            qa_output_tokens += _estimate_tokens(row.answer)

        chat_input_tokens = stt_tokens + qa_input_tokens
        chat_output_tokens = summary_tokens + qa_output_tokens
        stt_cost = (
            (float(recording.duration_ms) / 60000.0) * settings.price_stt_per_minute
            if recording.duration_ms
            else (stt_tokens / 1000.0) * (settings.price_stt_per_minute / 10.0)
        )
        estimated_cost_usd = (
            stt_cost
            + (chat_input_tokens / 1_000_000.0) * settings.price_chat_input_per_1m
            + (chat_output_tokens / 1_000_000.0) * settings.price_chat_output_per_1m
            + (embedding_tokens / 1_000_000.0) * settings.price_embedding_per_1m
        )
        total_tokens = stt_tokens + summary_tokens + embedding_tokens + qa_input_tokens + qa_output_tokens
        items.append(
            RecordingUsageItemOut(
                recording_id=recording.id,
                title=recording.title,
                created_at=recording.created_at,
                stt_tokens=stt_tokens,
                summary_tokens=summary_tokens,
                embedding_tokens=embedding_tokens,
                qa_input_tokens=qa_input_tokens,
                qa_output_tokens=qa_output_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=round(estimated_cost_usd, 6),
            )
        )

    used_tokens = sum(item.total_tokens for item in items)
    used_usd = sum(item.estimated_cost_usd for item in items)
    remaining_tokens = max(0, settings.token_budget_total - used_tokens)
    remaining_usd = max(0.0, settings.monthly_budget_usd - used_usd)
    return RecordingUsageOut(
        budget_tokens=settings.token_budget_total,
        used_tokens=used_tokens,
        remaining_tokens=remaining_tokens,
        budget_usd=settings.monthly_budget_usd,
        used_usd=round(used_usd, 6),
        remaining_usd=round(remaining_usd, 6),
        items=items,
    )


@router.get("", response_model=RecordingListOut)
def list_recordings(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["newest", "oldest"] = Query(default="newest"),
    view: Literal["all", "favorite", "trash"] = Query(default="all"),
    folder: str | None = Query(default=None, max_length=120),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingListOut:
    _purge_expired_trash(db, user_id)
    query = db.query(Recording).filter(Recording.user_id == user_id)
    if view == "trash":
        query = query.filter(Recording.deleted_at.is_not(None))
    else:
        query = query.filter(Recording.deleted_at.is_(None))
        if view == "favorite":
            query = query.filter(Recording.is_favorite.is_(True))
        if folder and folder.strip():
            query = query.filter(Recording.folder_name == folder.strip())

    if q:
        lowered = q.strip().lower()
        if lowered:
            query = query.filter(func.lower(func.coalesce(Recording.title, "")).contains(lowered))

    ordering = desc(Recording.created_at) if sort == "newest" else asc(Recording.created_at)
    items = query.order_by(ordering).offset(offset).limit(limit).all()
    return RecordingListOut(items=items)


@router.post("", response_model=RecordingOut)
def create_recording(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source: str = Form(default="upload"),
    note_md: str = Form(default=""),
    folder_name: str | None = Form(default=None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    bucket, key, mime = upload_to_s3(file)
    recording = Recording(
        user_id=user_id,
        title=title,
        source=source,
        s3_bucket=bucket,
        s3_key=key,
        mime_type=mime,
        status="uploaded",
        progress=5,
        note_md=note_md or "",
        folder_name=(folder_name or "").strip() or None,
    )
    db.add(recording)
    db.commit()
    db.refresh(recording)
    enqueue_pipeline(recording.id)
    db.refresh(recording)
    return recording


@router.get("/{recording_id}", response_model=RecordingDetailOut)
def get_recording(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingDetailOut:
    return _get_owned_recording(db, recording_id, user_id)


@router.post("/{recording_id}/retry", response_model=RecordingOut)
def retry_recording_analysis(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    recording = _get_owned_recording(db, recording_id, user_id)
    if recording.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deleted recording cannot be retried")
    if recording.status in {"uploaded", "transcribing", "transcribed", "summarizing", "indexing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Analysis is already in progress")

    recording.status = "uploaded"
    recording.progress = 5
    recording.error_message = None
    db.commit()
    db.refresh(recording)

    enqueue_pipeline(recording.id)
    db.refresh(recording)
    return recording


@router.patch("/{recording_id}", response_model=RecordingOut)
def update_recording(
    recording_id: str,
    payload: RecordingUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    recording = _get_owned_recording(db, recording_id, user_id)
    next_title = payload.title.strip()
    recording.title = next_title or None
    db.commit()
    db.refresh(recording)
    return recording


@router.patch("/{recording_id}/favorite", response_model=RecordingOut)
def update_favorite(
    recording_id: str,
    payload: RecordingFavoriteUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    recording = _get_owned_recording(db, recording_id, user_id)
    recording.is_favorite = payload.is_favorite
    db.commit()
    db.refresh(recording)
    return recording


@router.patch("/{recording_id}/folder", response_model=RecordingOut)
def update_folder(
    recording_id: str,
    payload: RecordingFolderUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    recording = _get_owned_recording(db, recording_id, user_id)
    recording.folder_name = (payload.folder_name or "").strip() or None
    db.commit()
    db.refresh(recording)
    return recording


@router.patch("/{recording_id}/note", response_model=RecordingOut)
def update_note(
    recording_id: str,
    payload: RecordingNoteUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    recording = _get_owned_recording(db, recording_id, user_id)
    recording.note_md = payload.note_md
    db.commit()
    db.refresh(recording)
    return recording


@router.post("/{recording_id}/restore", response_model=RecordingOut)
def restore_recording(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingOut:
    recording = _get_owned_recording(db, recording_id, user_id)
    recording.deleted_at = None
    db.commit()
    db.refresh(recording)
    return recording


@router.delete("/{recording_id}/purge", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def purge_recording(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    recording = _get_owned_recording(db, recording_id, user_id)
    _hard_delete_recording(db, recording)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_recording(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    recording = _get_owned_recording(db, recording_id, user_id)
    recording.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{recording_id}/audio")
def get_audio(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    recording = _get_owned_recording(db, recording_id, user_id)
    payload = read_object_bytes(recording.s3_bucket, recording.s3_key)
    filename = _recording_label(recording).replace(" ", "_")
    encoded_filename = quote(filename, safe="")
    headers = {
        "Content-Disposition": f'inline; filename="{recording.id}"; filename*=UTF-8\'\'{encoded_filename}'
    }
    return StreamingResponse(io.BytesIO(payload), media_type=recording.mime_type, headers=headers)


@router.get("/{recording_id}/transcript", response_model=TranscriptOut)
def get_transcript(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> TranscriptOut:
    _get_owned_recording(db, recording_id, user_id)
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not ready")
    normalized = _normalized_segments(transcript.segments or [])
    if normalized != (transcript.segments or []):
        transcript.segments = normalized
        transcript.full_text = " ".join(segment["text"] for segment in normalized)
        db.commit()
    return TranscriptOut(
        recording_id=recording_id,
        language=transcript.language,
        full_text=transcript.full_text,
        segments=normalized,
    )


@router.patch("/{recording_id}/segments", response_model=TranscriptOut)
def update_transcript_segments(
    recording_id: str,
    payload: TranscriptSegmentsUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> TranscriptOut:
    _get_owned_recording(db, recording_id, user_id)
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not ready")
    normalized = _normalized_segments([segment.model_dump() for segment in payload.segments])
    transcript.segments = normalized
    transcript.full_text = " ".join(segment["text"] for segment in normalized)
    db.commit()
    return TranscriptOut(
        recording_id=recording_id,
        language=transcript.language,
        full_text=transcript.full_text,
        segments=normalized,
    )


@router.get("/{recording_id}/summary", response_model=SummaryOut)
def get_summary(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SummaryOut:
    _get_owned_recording(db, recording_id, user_id)
    summary = db.query(Summary).filter(Summary.recording_id == recording_id).first()
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not ready")
    return SummaryOut(
        recording_id=recording_id,
        summary_md=summary.summary_md,
        action_items=summary.action_items,
        keywords=summary.keywords,
        timeline=summary.timeline,
    )


@router.post("/{recording_id}/qa", response_model=QAResponse)
def ask_question(
    recording_id: str,
    payload: QARequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> QAResponse:
    recording = _get_owned_recording(db, recording_id, user_id)
    if recording.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Index not ready")
    try:
        return answer_question(db, recording_id, user_id, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{recording_id}/qa/messages", response_model=QAHistoryResponse)
def get_qa_history(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> QAHistoryResponse:
    _get_owned_recording(db, recording_id, user_id)
    rows = (
        db.query(QAMessage)
        .filter(QAMessage.recording_id == recording_id, QAMessage.user_id == user_id)
        .order_by(QAMessage.created_at.asc())
        .all()
    )
    items = [
        QATurnOut(
            id=row.id,
            question=row.question,
            answer=row.answer,
            citations=row.citations,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return QAHistoryResponse(items=items)
