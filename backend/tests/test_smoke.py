from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_recording_flow() -> None:
    client = TestClient(app)
    headers = {"x-user-id": "u1"}

    create = client.post(
        "/recordings",
        headers=headers,
        files={"file": ("lecture.wav", b"bytes", "audio/wav")},
        data={"title": "os class"},
    )
    assert create.status_code == 200
    recording_id = create.json()["id"]

    metadata = client.get(f"/recordings/{recording_id}", headers=headers)
    assert metadata.status_code == 200
    assert metadata.json()["status"] == "ready"

    transcript = client.get(f"/recordings/{recording_id}/transcript", headers=headers)
    assert transcript.status_code == 200
    assert len(transcript.json()["segments"]) > 0

    summary = client.get(f"/recordings/{recording_id}/summary", headers=headers)
    assert summary.status_code == 200
    assert "one_liner" in summary.json()

    qa = client.post(
        f"/recordings/{recording_id}/qa",
        headers=headers,
        json={"question": "다음 액션은 뭐야?"},
    )
    assert qa.status_code == 200
    assert len(qa.json()["citations"]) > 0
