from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.models import QAMessage, Recording, Summary, Transcript
from app.db.session import get_db
from app.schemas.qa import QAHistoryResponse, QARequest, QAResponse, QATurnOut
from app.schemas.recording import (
    RecordingDetailOut,
    RecordingListOut,
    RecordingOut,
    SummaryOut,
    TranscriptOut,
)
from app.services.rag import answer_question
from app.services.storage import upload_to_s3
from app.tasks.jobs import enqueue_pipeline

router = APIRouter()


def _get_owned_recording(db: Session, recording_id: str, user_id: str) -> Recording:
    recording = (
        db.query(Recording)
        .filter(Recording.id == recording_id, Recording.user_id == user_id)
        .first()
    )
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return recording


@router.get("", response_model=RecordingListOut)
def list_recordings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecordingListOut:
    items = (
        db.query(Recording)
        .filter(Recording.user_id == user_id)
        .order_by(Recording.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
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
