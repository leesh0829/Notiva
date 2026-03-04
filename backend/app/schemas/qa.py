from datetime import datetime

from pydantic import BaseModel, Field


class QARequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class CitationOut(BaseModel):
    chunk_id: str
    text: str
    start_ms: int
    end_ms: int
    score: float


class QAResponse(BaseModel):
    answer: str
    citations: list[CitationOut]


class QATurnOut(BaseModel):
    id: str
    question: str
    answer: str
    citations: list[CitationOut]
    created_at: datetime


class QAHistoryResponse(BaseModel):
    items: list[QATurnOut]

