from __future__ import annotations


def summarize(transcript_text: str) -> dict:
    _ = transcript_text
    return {
        "title": "주간 프로젝트 회의",
        "one_liner": "진행 상황과 후속 액션을 점검한 회의입니다.",
        "topics": ["진행 현황", "리스크", "다음 액션"],
        "key_points": ["기능 개발 70% 완료", "QA 일정 재조정 필요"],
        "decisions": ["금요일까지 테스트 범위 확정"],
        "action_items": [
            {"task": "테스트 케이스 정리", "owner": "팀A", "due": "2026-03-07"}
        ],
        "timeline": [
            {"t_start_sec": 0, "t_end_sec": 60, "summary": "진행 상황 및 액션 아이템 논의"}
        ],
        "open_questions": ["외부 연동 QA 일정 확정 필요"],
    }
