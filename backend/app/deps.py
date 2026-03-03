from fastapi import Header, HTTPException


def current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="x-user-id header is required")
    return x_user_id
