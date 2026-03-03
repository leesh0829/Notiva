from __future__ import annotations


def transcribe(audio_url: str) -> dict:
    # Placeholder STT integration (Whisper/Deepgram/etc.)
    _ = audio_url
    segments = [
        {"t_start_sec": 0, "t_end_sec": 30, "text": "이번 주 프로젝트 진행 상황을 공유합니다."},
        {"t_start_sec": 31, "t_end_sec": 60, "text": "다음 액션 아이템과 담당자를 정리합시다."},
    ]
    return {
        "language": "ko",
        "full_text": " ".join([s["text"] for s in segments]),
        "segments": segments,
    }
