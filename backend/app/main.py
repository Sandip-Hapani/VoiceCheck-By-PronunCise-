"""FastAPI application for the VoiceCheck processing pipeline.

Responsibilities:
  * Load the Whisper model and submission store once at startup.
  * Accept an audio upload, persist it, and kick off background processing.
  * Serve uploaded audio back for teacher playback.
  * Expose read endpoints so the API can be inspected via Swagger (``/docs``)
    without the frontend.

The frontend never talks to Whisper or the LLM directly — it uploads here and
then watches Firestore for the result.

Local dev: if Whisper or Firebase aren't available the app still boots, using a
mock transcriber and an in-memory store, so every endpoint is exercisable from
Swagger. Watch the startup logs to see which backends are active.
"""
from __future__ import annotations

import logging
import os
import uuid
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
from fastapi.responses import FileResponse, RedirectResponse

from .audio_storage import AudioStorage, create_audio_storage
from .config import Settings, get_settings
from .pipeline import process_submission
from .schemas import SubmissionCreated, SubmissionDetail
from .store import SubmissionStore, create_store
from .transcription import TranscriberProtocol, create_transcriber

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 15 * 1024 * 1024  # ~15 MB ceiling for a 30s clip

API_DESCRIPTION = """
Processing pipeline for **VoiceCheck**.

**Flow:** upload audio → a `processing` submission is created → Whisper
transcribes it → an LLM generates structured feedback → the submission is marked
`done`. The frontend tracks this live via a Firestore real-time listener.

Use **POST `/api/submissions`** to submit a clip (set `VERIFY_AUTH=false` for
quick testing without a Firebase token), then **GET `/api/submissions/{id}`** to
watch the status flip to `done`.
"""

tags_metadata = [
    {"name": "submissions", "description": "Create and inspect submissions."},
    {"name": "audio", "description": "Serve uploaded audio for playback."},
    {"name": "health", "description": "Liveness check."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    os.makedirs(settings.audio_store_dir, exist_ok=True)

    # Load the heavy resources exactly once (with dev fallbacks).
    transcriber = create_transcriber(settings.whisper_model)
    store = create_store(settings)
    audio_storage = create_audio_storage(settings)

    app.state.settings = settings
    app.state.transcriber = transcriber
    app.state.store = store
    app.state.audio_storage = audio_storage

    # Loud, explicit summary so it's obvious whether the frontend will see this
    # backend's data. The frontend reads real (cloud) Firestore — if this backend
    # is on the in-memory store, the two are NOT sharing data.
    store_kind = type(store).__name__
    logger.info(
        "VoiceCheck ready | store=%s | audio=%s | transcriber=%s",
        store_kind,
        type(audio_storage).__name__,
        type(transcriber).__name__,
    )
    if store_kind == "InMemoryStore":
        logger.warning(
            "Backend is using the IN-MEMORY store. The frontend reads cloud "
            "Firestore, so it will NOT see these submissions, and data is lost "
            "on restart. Install firebase-admin and set "
            "GOOGLE_APPLICATION_CREDENTIALS to use the shared cloud Firestore."
        )
    yield


app = FastAPI(
    title="VoiceCheck API",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)


def get_app_settings() -> Settings:
    return app.state.settings


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _authenticate(
    authorization: str | None, settings: Settings, store: SubmissionStore
) -> dict:
    """Verify the Firebase ID token and return its decoded claims.

    Skips verification when ``VERIFY_AUTH=false`` or when the active store can't
    verify tokens (in-memory dev mode), returning a stub identity instead.
    """
    if not settings.verify_auth or not getattr(store, "can_verify_tokens", False):
        return {"email": "dev@local", "uid": "dev-user"}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    try:
        return store.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid token") from exc


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/submissions", response_model=SubmissionCreated, tags=["submissions"])
async def create_submission(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(..., description="Audio clip (webm/opus), <= ~30s"),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> SubmissionCreated:
    """Accept an audio upload and start async transcription + feedback."""
    store: SubmissionStore = app.state.store
    transcriber: TranscriberProtocol = app.state.transcriber
    audio_storage: AudioStorage = app.state.audio_storage

    claims = _authenticate(authorization, settings, store)

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large")

    # Persist the audio (Firebase Storage when configured, else local) and get a
    # playback URL for the frontend.
    audio_key = uuid.uuid4().hex
    audio_url = audio_storage.store(audio_key, data)

    submission_id = store.create_submission(
        student_email=claims.get("email", "unknown"),
        student_uid=claims.get("uid", "unknown"),
        audio_url=audio_url,
    )

    # Whisper is CPU-bound; BackgroundTasks runs this sync fn in a worker thread.
    background_tasks.add_task(
        process_submission,
        submission_id=submission_id,
        audio_key=audio_key,
        audio_storage=audio_storage,
        transcriber=transcriber,
        firestore=store,
        settings=settings,
    )

    return SubmissionCreated(id=submission_id, status="processing")


@app.get(
    "/api/submissions",
    response_model=list[SubmissionDetail],
    tags=["submissions"],
)
def list_submissions() -> list[dict]:
    """List all submissions (newest first). Handy for Swagger/debugging."""
    store: SubmissionStore = app.state.store
    return store.list_submissions()


@app.get(
    "/api/submissions/{submission_id}",
    response_model=SubmissionDetail,
    tags=["submissions"],
)
def get_submission(submission_id: str) -> dict:
    """Fetch a single submission — poll this to watch status reach `done`."""
    store: SubmissionStore = app.state.store
    doc = store.get_submission(submission_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return doc


@app.get("/api/audio/{submission_id}", tags=["audio"])
def get_audio(
    submission_id: str,
    settings: Settings = Depends(get_app_settings),
) -> FileResponse:
    """Fetch a single submission — poll this to watch status reach `done`."""
    store: SubmissionStore = app.state.store
    doc = store.get_submission(submission_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    """Stream the stored audio for a submission."""
    audio_url = doc.get("audioUrl")
    print(f"Audio URL for submission {submission_id}: {audio_url}")
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio URL not found for submission")
    
    # Extract audio_id from audio_url
    audio_id = audio_url.split("/")[-1].split(".")[0]
    
    # Guard against path traversal — ids are store-generated tokens.
    if not audio_id.isalnum():
        raise HTTPException(status_code=400, detail="No Audio Found (Invalid ID)")
    
    audio_path = os.path.join(settings.audio_store_dir, f"{audio_id}.webm")
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(audio_path, media_type="audio/webm")
