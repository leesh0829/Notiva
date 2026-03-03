from fastapi import FastAPI

from app.api.routes.recordings import router as recordings_router

app = FastAPI(title="Recording AI API", version="0.1.0")
app.include_router(recordings_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
