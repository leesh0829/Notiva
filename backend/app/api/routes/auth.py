from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import create_access_token

router = APIRouter()


class DevTokenRequest(BaseModel):
    user_id: str


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/dev-token", response_model=DevTokenResponse)
def issue_dev_token(payload: DevTokenRequest) -> DevTokenResponse:
    if settings.app_env.lower() == "prod" or not settings.enable_dev_auth_routes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    try:
        UUID(payload.user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id must be UUID",
        ) from exc
    token = create_access_token(payload.user_id)
    return DevTokenResponse(access_token=token)

