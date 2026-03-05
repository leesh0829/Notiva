from __future__ import annotations

import hashlib
import math

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Transcript, TranscriptChunk
from app.services.chunking import chunk_transcript_segments
from app.services.openai_client import get_openai_client

EMBEDDING_BATCH_MAX_CHARS = 6000


def deterministic_embedding(text: str, dim: int | None = None) -> list[float]:
    target_dim = dim or settings.embedding_dim
    values: list[float] = []
    seed = text.encode("utf-8")
    counter = 0
    while len(values) < target_dim:
        digest = hashlib.sha256(seed + str(counter).encode("utf-8")).digest()
        for idx in range(0, len(digest), 4):
            raw = int.from_bytes(digest[idx : idx + 4], "little", signed=False)
            values.append((raw / 4294967295.0) * 2.0 - 1.0)
            if len(values) == target_dim:
                break
        counter += 1

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = get_openai_client()
    clean = [text for text in texts if text.strip()]
    if not clean:
        return []
    if client is not None:
        vectors: list[list[float]] = []
        batch: list[str] = []
        used_chars = 0
        for text in clean:
            # Keep each provider call below safe context size.
            if batch and used_chars + len(text) > EMBEDDING_BATCH_MAX_CHARS:
                response = client.embeddings.create(
                    model=settings.openai_embed_model,
                    input=batch,
                )
                vectors.extend(item.embedding for item in response.data)
                batch = []
                used_chars = 0
            batch.append(text)
            used_chars += len(text)

        if batch:
            response = client.embeddings.create(
                model=settings.openai_embed_model,
                input=batch,
            )
            vectors.extend(item.embedding for item in response.data)
        return vectors
    return [deterministic_embedding(text) for text in clean]


def embed_text(text: str) -> list[float]:
    items = embed_texts([text])
    return items[0] if items else deterministic_embedding(text)


def build_chunk_index(db: Session, recording_id: str) -> None:
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise ValueError("Transcript not found")

    db.query(TranscriptChunk).filter(TranscriptChunk.recording_id == recording_id).delete()

    chunk_items = chunk_transcript_segments(
        transcript.segments,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    contents = [str(chunk["text"]) for chunk in chunk_items]
    vectors = embed_texts(contents)

    for idx, chunk_item in enumerate(chunk_items):
        content = str(chunk_item["text"])
        embedding = vectors[idx]
        chunk = TranscriptChunk(
            recording_id=recording_id,
            transcript_id=transcript.id,
            chunk_index=idx,
            start_ms=int(chunk_item["start_ms"]),
            end_ms=int(chunk_item["end_ms"]),
            content=content,
            token_count=max(1, len(content) // 4),
            embedding=embedding,
        )
        db.add(chunk)
    db.commit()
