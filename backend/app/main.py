"""FastAPI application for the VoiceCheck processing pipeline.

Responsibilities:
  * Load the Whisper model and Firestore client once at startup.
  * Accept an audio upload, persist it, and kick off background processing.
  * Serve uploaded audio back for teacher playback.

The frontend never talks to Whisper or the LLM directly — it uploads here and
then watches Firestore for the result.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .firestore_client import FirestoreClient
from .pipeline import process_submission
from .schemas import SubmissionCreated
from .transcription import Transcriber

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 15 * 1024 * 1024  # ~15 MB ceiling for a 30s clip


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    os.makedirs(settings.audio_store_dir, exist_ok=True)

    # Load the heavy resources exactly once.
    transcriber = Transcriber(settings.whisper_model)
    transcriber.load()
    firestore = FirestoreClient(settings)

    app.state.settings = settings
    app.state.transcriber = transcriber
    app.state.firestore = firestore
    logger.info("VoiceCheck backend ready.")
    yield


app = FastAPI(title="VoiceCheck API", lifespan=lifespan)


def get_app_settings() -> Settings:
    return app.state.settings


app.add_middleware(
    CORSMiddleware,
    # CORS list is resolved lazily at request time via the settings object,
    # but middleware needs the value at construction; read it from env here.
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _authenticate(authorization: str | None, settings: Settings, firestore: FirestoreClient) -> dict:
    """Verify the Firebase ID token and return its decoded claims.

    Honours ``VERIFY_AUTH=false`` for local smoke tests.
    """
    if not settings.verify_auth:
        return {"email": "dev@local", "uid": "dev-user"}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    try:
        return firestore.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid token") from exc


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/submissions", response_model=SubmissionCreated)
async def create_submission(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> SubmissionCreated:
    firestore: FirestoreClient = app.state.firestore
    transcriber: Transcriber = app.state.transcriber

    claims = _authenticate(authorization, settings, firestore)

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large")

    submission_id = firestore.create_submission(
        student_email=claims.get("email", "unknown"),
        student_uid=claims.get("uid", "unknown"),
    )

    audio_path = os.path.join(settings.audio_store_dir, f"{submission_id}.webm")
    with open(audio_path, "wb") as f:
        f.write(data)

    # Whisper is CPU-bound; BackgroundTasks runs this sync fn in a worker thread.
    background_tasks.add_task(
        process_submission,
        submission_id=submission_id,
        audio_path=audio_path,
        transcriber=transcriber,
        firestore=firestore,
        settings=settings,
    )

    return SubmissionCreated(id=submission_id, status="processing")


@app.get("/api/audio/{submission_id}")
def get_audio(
    submission_id: str,
    settings: Settings = Depends(get_app_settings),
) -> FileResponse:
    # Guard against path traversal — ids are Firestore-generated tokens.
    if not submission_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid id")

    audio_path = os.path.join(settings.audio_store_dir, f"{submission_id}.webm")
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(audio_path, media_type="audio/webm")
