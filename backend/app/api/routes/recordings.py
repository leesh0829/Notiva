from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.deps import current_user_id
from app.models import Recording, db
from app.schemas import (
    QAPayload,
    QAResponse,
    RecordingCreateResponse,
    RecordingMetadataResponse,
    SummaryResponse,
    TranscriptResponse,
)
from app.services.rag import answer_with_citations
from app.worker.tasks import run_pipeline

router = APIRouter(prefix="/recordings", tags=["recordings"])


@router.post("", response_model=RecordingCreateResponse)
async def create_recording(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user_id: str = Depends(current_user_id),
) -> RecordingCreateResponse:
    recording_id = str(uuid4())
    audio_url = f"s3://placeholder-bucket/{recording_id}/{file.filename}"
    recording = Recording(
        id=recording_id,
        user_id=user_id,
        title=title,
        audio_url=audio_url,
        status="uploaded",
    )
    db.recordings[recording_id] = recording

    # MVP sync pipeline call; replace with Celery queue send in production.
    run_pipeline(recording_id)
    return RecordingCreateResponse(id=recording_id, status=db.recordings[recording_id].status)


@router.get("/{recording_id}", response_model=RecordingMetadataResponse)
def get_recording(recording_id: str, user_id: str = Depends(current_user_id)) -> RecordingMetadataResponse:
    recording = db.recordings.get(recording_id)
    if not recording or recording.user_id != user_id:
        raise HTTPException(status_code=404, detail="recording not found")
    return RecordingMetadataResponse(
        id=recording.id,
        title=recording.title,
        status=recording.status,
        duration_sec=recording.duration_sec,
        created_at=recording.created_at,
    )


@router.get("/{recording_id}/transcript", response_model=TranscriptResponse)
def get_transcript(recording_id: str, user_id: str = Depends(current_user_id)) -> TranscriptResponse:
    recording = db.recordings.get(recording_id)
    if not recording or recording.user_id != user_id:
        raise HTTPException(status_code=404, detail="recording not found")
    transcript = db.transcripts.get(recording_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="transcript not ready")
    return TranscriptResponse(
        recording_id=recording_id,
        full_text=transcript.full_text,
        segments=transcript.segments,
        language=transcript.language,
    )


@router.get("/{recording_id}/summary", response_model=SummaryResponse)
def get_summary(recording_id: str, user_id: str = Depends(current_user_id)) -> SummaryResponse:
    recording = db.recordings.get(recording_id)
    if not recording or recording.user_id != user_id:
        raise HTTPException(status_code=404, detail="recording not found")
    summary = db.summaries.get(recording_id)
    if not summary:
        raise HTTPException(status_code=404, detail="summary not ready")
    return SummaryResponse(**summary.summary_json)


@router.post("/{recording_id}/qa", response_model=QAResponse)
def ask_qa(
    recording_id: str,
    payload: QAPayload,
    user_id: str = Depends(current_user_id),
) -> QAResponse:
    recording = db.recordings.get(recording_id)
    if not recording or recording.user_id != user_id:
        raise HTTPException(status_code=404, detail="recording not found")
    transcript = db.transcripts.get(recording_id)
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript not ready")
    answer, citations = answer_with_citations(payload.question, transcript.segments)
    return QAResponse(answer=answer, citations=citations)
