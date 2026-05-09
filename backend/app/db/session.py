from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolved_database_url() -> str:
    db_url = settings.database_url
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return db_url
    raw_path = db_url[len(prefix) :]
    if raw_path == ":memory:":
        return db_url
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = (_BACKEND_DIR / db_path).resolve()
    return f"{prefix}{db_path.as_posix()}"


DATABASE_URL = _resolved_database_url()

engine_kwargs: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
