from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.models import QAMessage, Recording, Summary, Transcript, TranscriptChunk
from app.db.session import get_db
from app.schemas.qa import QAHistoryResponse, QARequest, QAResponse, QATurnOut
from app.schemas.recording import (
    RecordingDetailOut,
    RecordingListOut,
    RecordingOut,
    RecordingUpdateRequest,
    SummaryOut,
    TranscriptOut,
)
from app.services.rag import answer_question
from app.services.storage import upload_to_s3
from app.tasks.jobs import enqueue_pipeline

router = APIRouter()


def _get_owned_recording(db: Session, recording_id: str, user_id: str) -> Recording:
    recording = db.query(Recording).filter(Recording.id == recording_id, Recording.user_id == user_id).first()
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return recording


@router.get("", response_model=RecordingListOut)
def list_recordings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["newest", "oldest"] = Query(default="newest"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingListOut:
    query = db.query(Recording).filter(Recording.user_id == user_id)
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


@router.delete(
    "/{recording_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_recording(
    recording_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    recording = _get_owned_recording(db, recording_id, user_id)
    db.query(QAMessage).filter(QAMessage.recording_id == recording_id).delete()
    db.query(TranscriptChunk).filter(TranscriptChunk.recording_id == recording_id).delete()
    db.query(Summary).filter(Summary.recording_id == recording_id).delete()
    db.query(Transcript).filter(Transcript.recording_id == recording_id).delete()
    db.delete(recording)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    return TranscriptOut(
        recording_id=recording_id,
        language=transcript.language,
        full_text=transcript.full_text,
        segments=transcript.segments,
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
