from app.services.stt import _is_invalid_audio_error


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

