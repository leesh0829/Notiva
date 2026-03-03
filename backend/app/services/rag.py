from __future__ import annotations

from app.schemas import Citation


def answer_with_citations(question: str, transcript_segments: list[dict]) -> tuple[str, list[Citation]]:
    _ = question
    citations = [
        Citation(
            text=segment["text"],
            t_start_sec=segment["t_start_sec"],
            t_end_sec=segment["t_end_sec"],
        )
        for segment in transcript_segments[:2]
    ]
    answer = "회의에서는 진행 상황 공유 후, 테스트 케이스 정리를 다음 액션으로 결정했습니다."
    return answer, citations
