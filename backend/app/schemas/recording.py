from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RecordingStatus = Literal[
    "uploaded",
    "transcribing",
    "transcribed",
    "summarizing",
    "indexing",
    "ready",
    "failed",
]


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    source: str
    status: RecordingStatus
    progress: int
    created_at: datetime


class RecordingDetailOut(RecordingOut):
    duration_ms: int | None = None
    error_message: str | None = None


class RecordingListOut(BaseModel):
    items: list[RecordingOut]


class RecordingUpdateRequest(BaseModel):
    title: str = Field(default="", max_length=300)


class TranscriptSegmentOut(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class TranscriptOut(BaseModel):
    recording_id: str
    language: str | None = None
    full_text: str
    segments: list[TranscriptSegmentOut]


class TimelineItemOut(BaseModel):
    time_ms: int
    text: str


class SummaryOut(BaseModel):
    recording_id: str
    summary_md: str
    action_items: list[dict] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    timeline: list[TimelineItemOut] = Field(default_factory=list)
