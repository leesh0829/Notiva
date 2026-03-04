import os
from pathlib import Path

from fastapi.testclient import TestClient

# Test env must be set before app import.
TEST_DB_PATH = Path(__file__).parent / "test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
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


def test_register_login_and_me() -> None:
    register = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "test-password-123"},
    )
    assert register.status_code == 201
    register_payload = register.json()
    assert register_payload["user"]["email"] == "user@example.com"
    assert register_payload["access_token"]

    login = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "test-password-123"},
    )
    assert login.status_code == 200
    login_payload = login.json()
    token = login_payload["access_token"]
    assert token

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    me_payload = me.json()
    assert me_payload["email"] == "user@example.com"


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

    updated = client.patch(
        f"/recordings/{recording_id}",
        headers=headers,
        json={"title": "updated title"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "updated title"

    listed = client.get("/recordings?limit=50&q=updated&sort=oldest", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == recording_id for item in listed.json()["items"])

    deleted = client.delete(f"/recordings/{recording_id}", headers=headers)
    assert deleted.status_code == 204

    listed_after_delete = client.get("/recordings?view=all", headers=headers)
    assert listed_after_delete.status_code == 200
    assert all(item["id"] != recording_id for item in listed_after_delete.json()["items"])

    trash = client.get("/recordings?view=trash", headers=headers)
    assert trash.status_code == 200
    assert any(item["id"] == recording_id for item in trash.json()["items"])

    restored = client.post(f"/recordings/{recording_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None

    favorite = client.patch(
        f"/recordings/{recording_id}/favorite",
        headers=headers,
        json={"is_favorite": True},
    )
    assert favorite.status_code == 200
    assert favorite.json()["is_favorite"] is True

    usage = client.get("/recordings/usage", headers=headers)
    assert usage.status_code == 200
    assert "used_tokens" in usage.json()

    purged = client.delete(f"/recordings/{recording_id}/purge", headers=headers)
    assert purged.status_code == 204

    missing = client.get(f"/recordings/{recording_id}", headers=headers)
    assert missing.status_code == 404
