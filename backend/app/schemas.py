from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


RecordingStatus = Literal[
    "uploaded", "transcribing", "summarizing", "indexing", "ready", "failed"
]


class Citation(BaseModel):
    text: str
    t_start_sec: int = Field(ge=0)
    t_end_sec: int = Field(ge=0)


class QAPayload(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class QAResponse(BaseModel):
    answer: str
    citations: list[Citation]


class RecordingCreateResponse(BaseModel):
    id: str
    status: RecordingStatus


class RecordingMetadataResponse(BaseModel):
    id: str
    title: str | None = None
    status: RecordingStatus
    duration_sec: int | None = None
    created_at: datetime


class TranscriptSegment(BaseModel):
    t_start_sec: int = Field(ge=0)
    t_end_sec: int = Field(ge=0)
    text: str


class TranscriptResponse(BaseModel):
    recording_id: str
    language: str = "ko"
    full_text: str
    segments: list[TranscriptSegment]


class SummaryActionItem(BaseModel):
    task: str
    owner: str | None = None
    due: str | None = None


class SummaryTimeline(BaseModel):
    t_start_sec: int = Field(ge=0)
    t_end_sec: int = Field(ge=0)
    summary: str


class SummaryResponse(BaseModel):
    title: str
    one_liner: str
    topics: list[str]
    key_points: list[str]
    decisions: list[str]
    action_items: list[SummaryActionItem]
    timeline: list[SummaryTimeline]
    open_questions: list[str]
