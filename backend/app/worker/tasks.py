from __future__ import annotations

import logging

from app.models import db, Transcript, Summary
from app.services.stt import transcribe
from app.services.summarizer import summarize

logger = logging.getLogger(__name__)


def transcribe_task(recording_id: str) -> None:
    recording = db.recordings[recording_id]
    recording.status = "transcribing"
    tr = transcribe(recording.audio_url)
    db.transcripts[recording_id] = Transcript(
        recording_id=recording_id,
        full_text=tr["full_text"],
        segments=tr["segments"],
        language=tr["language"],
    )
    logger.info("Transcription finished for recording_id=%s", recording_id)


def summarize_task(recording_id: str) -> None:
    recording = db.recordings[recording_id]
    recording.status = "summarizing"
    transcript = db.transcripts[recording_id]
    summary_json = summarize(transcript.full_text)
    db.summaries[recording_id] = Summary(recording_id=recording_id, summary_json=summary_json)
    logger.info("Summarization finished for recording_id=%s", recording_id)


def embed_index_task(recording_id: str) -> None:
    recording = db.recordings[recording_id]
    recording.status = "indexing"
    # Placeholder: store embeddings in pgvector in production.
    recording.status = "ready"
    logger.info("Embedding index finished for recording_id=%s", recording_id)


def run_pipeline(recording_id: str) -> None:
    try:
        transcribe_task(recording_id)
        summarize_task(recording_id)
        embed_index_task(recording_id)
    except Exception:
        db.recordings[recording_id].status = "failed"
        logger.exception("Pipeline failed for recording_id=%s", recording_id)
        raise
