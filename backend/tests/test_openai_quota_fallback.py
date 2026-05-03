import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

# Test env must be set before app import.
TEST_DB_PATH = Path(__file__).parent / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
os.environ.setdefault("TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("LOCAL_STORAGE_DIR", str(Path(__file__).parent / ".tmp_storage"))
os.environ.setdefault("OPENAI_API_KEY", "")

from app.core.security import create_access_token
from app.db.base import Base
from app.db.models import Recording
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.embedding import deterministic_embedding, embed_texts
from app.services.rag import _llm_answer
from app.services.stt import run_transcription


client = TestClient(app)
Base.metadata.create_all(bind=engine)


class QuotaError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Error code: 429 - {'error': {'message': 'You exceeded your current quota, "
            "please check your plan and billing details.', 'type': 'insufficient_quota', "
            "'code': 'insufficient_quota'}}"
        )
        self.code = "insufficient_quota"
        self.body = {
            "error": {
                "message": "You exceeded your current quota, please check your plan and billing details.",
                "type": "insufficient_quota",
                "code": "insufficient_quota",
            }
        }


def test_run_transcription_falls_back_when_quota_is_exhausted() -> None:
    fake_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(QuotaError()))
        )
    )

    with (
        patch("app.services.stt.get_openai_client", return_value=fake_client),
        patch("app.services.stt.read_object_bytes", return_value=b"audio-bytes"),
        patch("app.services.stt._probe_duration_ms", return_value=0),
    ):
        text, segments, language = run_transcription("recordings", "sample.wav")

    assert "할당량이 소진" in text
    assert segments == [{"start_ms": 0, "end_ms": 0, "text": text}]
    assert language == "ko"


def test_embed_texts_falls_back_to_deterministic_vectors_on_quota_error() -> None:
    fake_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(QuotaError()))
    )

    with patch("app.services.embedding.get_openai_client", return_value=fake_client):
        vectors = embed_texts(["회의 요약", "액션 아이템"])

    assert vectors == [
        deterministic_embedding("회의 요약"),
        deterministic_embedding("액션 아이템"),
    ]


def test_llm_answer_uses_extractive_fallback_on_quota_error() -> None:
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(QuotaError()))
        )
    )
    top = [
        {
            "chunk": SimpleNamespace(
                content="테스트 범위를 이번 주 안에 확정한다.",
                start_ms=0,
                end_ms=1000,
            ),
            "score": 0.99,
        }
    ]

    with patch("app.services.rag.get_openai_client", return_value=fake_client):
        answer, picked = _llm_answer("다음 액션 아이템이 뭐야?", top, [])

    assert "테스트 범위를 이번 주 안에 확정한다." in answer
    assert picked == [0]


def test_recording_detail_sanitizes_stored_quota_error_message() -> None:
    token = create_access_token("00000000-0000-0000-0000-000000000001")
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/recordings",
        headers=headers,
        files={"file": ("quota.wav", b"audio-bytes", "audio/wav")},
        data={"title": "quota test", "source": "upload"},
    )
    assert create.status_code == 200
    recording_id = create.json()["id"]

    db = SessionLocal()
    try:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        assert recording is not None
        recording.status = "failed"
        recording.error_message = (
            "{'error': {'message': 'You exceeded your current quota, please check your plan and billing details.', "
            "'type': 'insufficient_quota', 'code': 'insufficient_quota'}}"
        )
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/recordings/{recording_id}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert "할당량이 소진" in payload["error_message"]
    assert "insufficient_quota" not in payload["error_message"]
