from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.recordings import router as recordings_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(recordings)")).all()
        columns = {row[1] for row in rows}
        if "is_favorite" not in columns:
            conn.execute(text("ALTER TABLE recordings ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT 0"))
        if "folder_name" not in columns:
            conn.execute(text("ALTER TABLE recordings ADD COLUMN folder_name VARCHAR(120)"))
        if "note_md" not in columns:
            conn.execute(text("ALTER TABLE recordings ADD COLUMN note_md TEXT NOT NULL DEFAULT ''"))
        if "deleted_at" not in columns:
            conn.execute(text("ALTER TABLE recordings ADD COLUMN deleted_at DATETIME"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(recordings_router, prefix="/recordings", tags=["recordings"])

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()

