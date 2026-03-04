import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthCredentials(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or not EMAIL_PATTERN.match(normalized):
            raise ValueError("Invalid email format")
        return normalized


class AuthUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut

