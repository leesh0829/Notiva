from __future__ import annotations

from collections.abc import Mapping

_QUOTA_TEXT_HINTS = (
    "insufficient_quota",
    "you exceeded your current quota",
    "check your plan and billing details",
)

_PUBLIC_QUOTA_ERROR_MESSAGE = (
    "OpenAI API 할당량이 소진되어 AI 분석을 완료하지 못했습니다. "
    "결제 또는 사용 한도를 확인한 뒤 'AI 재분석'을 다시 실행하세요."
)

_QUOTA_TRANSCRIPT_NOTICE = (
    "OpenAI API 할당량이 소진되어 실제 음성 전사를 생성하지 못했습니다. "
    "결제 또는 사용 한도를 확인한 뒤 'AI 재분석'을 다시 실행하세요."
)


def _contains_quota_hint(value: object) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and any(hint in text for hint in _QUOTA_TEXT_HINTS)


def _extract_error_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        nested = value.get("error")
        if isinstance(nested, Mapping):
            return nested
        return value
    return None


def is_insufficient_quota_error(error: object) -> bool:
    if _contains_quota_hint(error):
        return True

    for attr in ("body", "response", "error"):
        mapping = _extract_error_mapping(getattr(error, attr, None))
        if mapping and (
            _contains_quota_hint(mapping.get("code"))
            or _contains_quota_hint(mapping.get("type"))
            or _contains_quota_hint(mapping.get("message"))
        ):
            return True

    return _contains_quota_hint(getattr(error, "code", None))


def sanitize_provider_error_message(message: str | None) -> str | None:
    if not message:
        return message
    if is_insufficient_quota_error(message):
        return _PUBLIC_QUOTA_ERROR_MESSAGE
    return message


def quota_transcript_notice() -> str:
    return _QUOTA_TRANSCRIPT_NOTICE
