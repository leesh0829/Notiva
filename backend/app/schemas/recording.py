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
    is_favorite: bool = False
    folder_name: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime


class RecordingDetailOut(RecordingOut):
    duration_ms: int | None = None
    error_message: str | None = None
    note_md: str = ""


class RecordingListOut(BaseModel):
    items: list[RecordingOut]


class RecordingUpdateRequest(BaseModel):
    title: str = Field(default="", max_length=300)


class RecordingFavoriteUpdateRequest(BaseModel):
    is_favorite: bool


class RecordingFolderUpdateRequest(BaseModel):
    folder_name: str | None = Field(default=None, max_length=120)


class RecordingNoteUpdateRequest(BaseModel):
    note_md: str = Field(default="", max_length=100_000)


class TranscriptSegmentOut(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None


class TranscriptOut(BaseModel):
    recording_id: str
    language: str | None = None
    full_text: str
    segments: list[TranscriptSegmentOut]


class TranscriptSegmentsUpdateRequest(BaseModel):
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


class FolderItemOut(BaseModel):
    name: str
    count: int


class FolderListOut(BaseModel):
    items: list[FolderItemOut]


class RecordingUsageItemOut(BaseModel):
    recording_id: str
    title: str | None = None
    created_at: datetime
    stt_tokens: int
    summary_tokens: int
    embedding_tokens: int
    qa_input_tokens: int
    qa_output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class RecordingUsageOut(BaseModel):
    budget_tokens: int
    used_tokens: int
    remaining_tokens: int
    budget_usd: float
    used_usd: float
    remaining_usd: float
    items: list[RecordingUsageItemOut]
