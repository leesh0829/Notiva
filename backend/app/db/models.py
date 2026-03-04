from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base

try:
    if settings.database_url.startswith("postgresql"):
        from pgvector.sqlalchemy import Vector

        EMBEDDING_COLUMN_TYPE = Vector(settings.embedding_dim)
    else:
        EMBEDDING_COLUMN_TYPE = JSON
except Exception:
    EMBEDDING_COLUMN_TYPE = JSON


class RecordingStatus(str, Enum):
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    SUMMARIZING = "summarizing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class RecordingSource(str, Enum):
    UPLOAD = "upload"
    WEB_RECORD = "web_record"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default=RecordingSource.UPLOAD.value, nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=RecordingStatus.UPLOADED.value, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transcript: Mapped[Transcript | None] = relationship("Transcript", back_populates="recording", uselist=False)
    summary: Mapped[Summary | None] = relationship("Summary", back_populates="recording", uselist=False)


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    recording: Mapped[Recording] = relationship("Recording", back_populates="transcript")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    action_items: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    timeline: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    recording: Mapped[Recording] = relationship("Recording", back_populates="summary")


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    __table_args__ = (UniqueConstraint("recording_id", "chunk_index", name="uq_chunks_recording_chunk_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(EMBEDDING_COLUMN_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QAMessage(Base):
    __tablename__ = "qa_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
