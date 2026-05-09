from app.services.stt import _is_invalid_audio_error, _should_chunk_audio


class _FakeBadRequestError:
    def __init__(self, message: str) -> None:
        self._message = message

    def __str__(self) -> str:
        return self._message


def test_invalid_audio_error_detects_duration_limit() -> None:
    exc = _FakeBadRequestError(
        "Error code: 400 - {'error': {'message': 'audio duration 1438.554375 seconds is longer than "
        "1400 seconds which is the maximum for this model', 'type': 'invalid_request_error', 'code': "
        "'invalid_value'}}"
    )
    assert _is_invalid_audio_error(exc) is True


def test_should_chunk_audio_when_payload_exceeds_provider_limit() -> None:
    payload = b"x" * ((24 * 1024 * 1024) + 1)
    assert _should_chunk_audio(payload, duration_ms=0) is True


def test_should_chunk_audio_when_duration_exceeds_chunk_window() -> None:
    payload = b"x" * 1024
    assert _should_chunk_audio(payload, duration_ms=421_000) is True


def test_should_not_chunk_short_small_audio() -> None:
    payload = b"x" * 1024
    assert _should_chunk_audio(payload, duration_ms=180_000) is False
