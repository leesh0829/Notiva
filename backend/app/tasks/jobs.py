from __future__ import annotations

from celery import chain

from app.db.models import Recording, RecordingStatus, Transcript
from app.db.session import SessionLocal
from app.services.embedding import build_chunk_index
from app.services.stt import run_transcription
from app.services.summarize import run_summary
from app.tasks.celery_app import celery_app


def enqueue_pipeline(recording_id: str) -> None:
    chain(
        transcribe_task.s(recording_id),
        summarize_task.s(),
        embed_index_task.s(),
    ).apply_async()


def _update_status(recording: Recording, status: RecordingStatus, progress: int, message: str | None = None) -> None:
    recording.status = status.value
    recording.progress = progress
    recording.error_message = message


@celery_app.task(name="app.tasks.jobs.transcribe_task")
def transcribe_task(recording_id: str) -> str:
    db = SessionLocal()
    try:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            raise ValueError("Recording not found")

        _update_status(recording, RecordingStatus.TRANSCRIBING, 20)
        db.commit()

        full_text, segments, language = run_transcription(recording.s3_bucket, recording.s3_key)
        transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
        if transcript:
            transcript.full_text = full_text
            transcript.segments = segments
            transcript.language = language
        else:
            db.add(
                Transcript(
                    recording_id=recording_id,
                    full_text=full_text,
                    segments=segments,
                    language=language,
                )
            )

        _update_status(recording, RecordingStatus.TRANSCRIBED, 45)
        db.commit()
        return recording_id
    except Exception as exc:
        db.rollback()
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            _update_status(recording, RecordingStatus.FAILED, recording.progress, str(exc)[:500])
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.jobs.summarize_task")
def summarize_task(recording_id: str) -> str:
    db = SessionLocal()
    try:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            raise ValueError("Recording not found")

        _update_status(recording, RecordingStatus.SUMMARIZING, 60)
        db.commit()

        run_summary(db, recording_id)

        _update_status(recording, RecordingStatus.INDEXING, 80)
        db.commit()
        return recording_id
    except Exception as exc:
        db.rollback()
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            _update_status(recording, RecordingStatus.FAILED, recording.progress, str(exc)[:500])
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.jobs.embed_index_task")
def embed_index_task(recording_id: str) -> str:
    db = SessionLocal()
    try:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            raise ValueError("Recording not found")

        build_chunk_index(db, recording_id)
        _update_status(recording, RecordingStatus.READY, 100)
        db.commit()
        return recording_id
    except Exception as exc:
        db.rollback()
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            _update_status(recording, RecordingStatus.FAILED, recording.progress, str(exc)[:500])
            db.commit()
        raise
    finally:
        db.close()
