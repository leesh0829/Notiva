from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import AuthCredentials, AuthTokenOut, AuthUserOut

router = APIRouter()


class DevTokenRequest(BaseModel):
    user_id: str


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _issue_auth_response(user: User) -> AuthTokenOut:
    token = create_access_token(user.id)
    return AuthTokenOut(
        access_token=token,
        user=AuthUserOut.model_validate(user),
    )


@router.post("/register", response_model=AuthTokenOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: AuthCredentials,
    db: Session = Depends(get_db),
) -> AuthTokenOut:
    existing = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )
    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    user = User(email=payload.email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_auth_response(user)


@router.post("/login", response_model=AuthTokenOut)
def login(
    payload: AuthCredentials,
    db: Session = Depends(get_db),
) -> AuthTokenOut:
    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _issue_auth_response(user)


@router.get("/me", response_model=AuthUserOut)
def me(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AuthUserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AuthUserOut.model_validate(user)


@router.post("/dev-token", response_model=DevTokenResponse)
def issue_dev_token(payload: DevTokenRequest) -> DevTokenResponse:
    if settings.app_env.lower() in {"prod", "production"} or not settings.enable_dev_auth_routes:
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

