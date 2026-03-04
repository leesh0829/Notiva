import os
from pathlib import Path

from fastapi.testclient import TestClient

# Test env must be set before app import.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(__file__).parent / 'test.db'}")
os.environ.setdefault("TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("LOCAL_STORAGE_DIR", str(Path(__file__).parent / '.tmp_storage'))
os.environ.setdefault("OPENAI_API_KEY", "")

from app.core.security import create_access_token
from app.main import app
from app.db.base import Base
from app.db.session import engine


client = TestClient(app)
Base.metadata.create_all(bind=engine)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_issue_dev_token() -> None:
    response = client.post(
        "/auth/dev-token",
        json={"user_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]


def test_recording_smoke_flow() -> None:
    token = create_access_token("00000000-0000-0000-0000-000000000001")
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/recordings",
        headers=headers,
        files={"file": ("lecture.wav", b"audio-bytes", "audio/wav")},
        data={"title": "os class", "source": "upload"},
    )
    assert create.status_code == 200
    body = create.json()
    recording_id = body["id"]
    assert body["status"] in {"uploaded", "ready", "transcribing", "summarizing", "indexing", "transcribed"}

    detail = client.get(f"/recordings/{recording_id}", headers=headers)
    assert detail.status_code == 200

    transcript = client.get(f"/recordings/{recording_id}/transcript", headers=headers)
    assert transcript.status_code == 200
    assert len(transcript.json()["segments"]) > 0

    summary = client.get(f"/recordings/{recording_id}/summary", headers=headers)
    assert summary.status_code == 200
    assert "summary_md" in summary.json()

    qa = client.post(
        f"/recordings/{recording_id}/qa",
        headers=headers,
        json={"question": "다음 액션 아이템이 뭐야?"},
    )
    assert qa.status_code == 200
    qa_payload = qa.json()
    assert qa_payload["answer"]
    assert len(qa_payload["citations"]) > 0

    history = client.get(f"/recordings/{recording_id}/qa/messages", headers=headers)
    assert history.status_code == 200
    history_items = history.json()["items"]
    assert len(history_items) >= 1
    assert history_items[-1]["question"] == "다음 액션 아이템이 뭐야?"
