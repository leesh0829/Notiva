from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class Recording:
    id: str
    user_id: str
    title: str | None
    audio_url: str
    status: str
    duration_sec: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Transcript:
    recording_id: str
    full_text: str
    segments: list[dict]
    language: str = "ko"


@dataclass
class Summary:
    recording_id: str
    summary_json: dict


class InMemoryDB:
    def __init__(self) -> None:
        self.recordings: dict[str, Recording] = {}
        self.transcripts: dict[str, Transcript] = {}
        self.summaries: dict[str, Summary] = {}


db = InMemoryDB()
