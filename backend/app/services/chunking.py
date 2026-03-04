from __future__ import annotations


def chunk_transcript_segments(
    segments: list[dict],
    max_chars: int,
    overlap_chars: int,
) -> list[dict]:
    cleaned: list[dict] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start_ms = int(segment.get("start_ms", 0) or 0)
        end_ms = int(segment.get("end_ms", start_ms) or start_ms)
        cleaned.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})

    if not cleaned:
        return []

    chunks: list[dict] = []
    i = 0
    while i < len(cleaned):
        start_i = i
        items: list[dict] = []
        used = 0

        while i < len(cleaned):
            text = cleaned[i]["text"]
            add = len(text) + (1 if items else 0)
            if items and used + add > max_chars:
                break
            items.append(cleaned[i])
            used += add
            i += 1

        if not items:
            # Safety guard for very large single segment.
            items = [cleaned[i]]
            i += 1

        chunks.append(
            {
                "start_ms": items[0]["start_ms"],
                "end_ms": items[-1]["end_ms"],
                "text": " ".join(item["text"] for item in items),
            }
        )

        if i >= len(cleaned) or overlap_chars <= 0:
            continue

        # Rewind by overlap size so retrieval keeps local context continuity.
        rewind_chars = 0
        rewind_count = 0
        for item in reversed(items):
            rewind_chars += len(item["text"])
            rewind_count += 1
            if rewind_chars >= overlap_chars:
                break
        i = max(start_i + 1, i - rewind_count)

    return chunks

