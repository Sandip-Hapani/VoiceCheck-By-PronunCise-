"""Centralised, environment-driven configuration.

Everything that changes between local dev and production lives here so the rest
of the code never reads ``os.environ`` directly.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # development | production

    # --- Whisper -------------------------------------------------------
    whisper_model: str = "base"  # tiny | base | small | medium | large

    # --- LLM -------------------------------------------------------------
    # Groq is used when GROQ_API_KEY is set (free tier, no local GPU needed —
    # the hosted/production path). Otherwise the pipeline talks to a local
    # Ollama server (the offline dev path). If neither is reachable it falls
    # back to deterministic mock feedback so the app stays runnable either way.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    llm_timeout_seconds: float = 120.0

    # --- Firebase ----------------------------------------------------------
    # Path to a service-account JSON file. If empty, falls back to
    # GOOGLE_APPLICATION_CREDENTIALS_JSON (raw JSON contents — handy for
    # platforms with no file mounts, e.g. a Secret Manager value), then to
    # Application Default Credentials (e.g. on Cloud Run).
    google_application_credentials: str = ""
    google_application_credentials_json: str = ""
    # GCP project hosting Firestore. Only needed when the backend runs in a
    # *different* GCP project than Firestore (e.g. a Cloud Run service in
    # project A reading Firestore in project B) — otherwise ADC/the
    # credential file already know the right project.
    firestore_project_id: str = ""
    firestore_collection: str = "submissions"

    # Firebase Storage bucket for audio (e.g. "my-project.appspot.com" or
    # "my-project.firebasestorage.app"). When set, audio is uploaded there and
    # the frontend plays it from a Firebase download URL. When empty, audio
    # falls through to Cloudflare R2 (if configured) or local disk.
    firebase_storage_bucket: str = ""

    # --- Cloudflare R2 (optional persistent audio storage) -----------------
    # S3-compatible, free tier (10GB). Checked after firebase_storage_bucket
    # and before local disk — use this on hosts with ephemeral/no disk (e.g.
    # Cloud Run). Leave empty to skip.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_base_url: str = ""  # e.g. https://pub-xxxx.r2.dev or a custom domain

    # --- Auth --------------------------------------------------------------
    # Verify the Firebase ID token on every upload. Can be disabled for quick
    # local smoke tests where you don't want to wire up a real token.
    verify_auth: bool = True

    # --- Storage -----------------------------------------------------------
    # Where uploaded audio is persisted locally and the public base URL the
    # frontend uses to play it back. Used only when no Firebase/R2 bucket is
    # configured (see app/audio_storage.py).
    audio_store_dir: str = "audio_store"
    public_base_url: str = "http://localhost:8000"

    # --- CORS --------------------------------------------------------------
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
