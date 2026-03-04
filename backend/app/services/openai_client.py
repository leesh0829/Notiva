from functools import lru_cache

from openai import OpenAI

from app.core.config import settings


@lru_cache
def get_openai_client() -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_sec)

