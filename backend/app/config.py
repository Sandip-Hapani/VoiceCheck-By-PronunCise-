"""Centralised, environment-driven configuration.

Everything that changes between local dev and production lives here so the rest
of the code never reads ``os.environ`` directly.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Whisper -----------------------------------------------------------
    whisper_model: str = "base"  # tiny | base | small | medium | large

    # --- LLM (Ollama) ------------------------------------------------------
    # When Ollama is unreachable the pipeline falls back to deterministic
    # mock feedback so the app stays runnable without any local model.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_timeout_seconds: float = 120.0

    # --- Firebase ----------------------------------------------------------
    # Path to a service-account JSON. If empty, firebase-admin falls back to
    # Application Default Credentials (e.g. on Cloud Run).
    google_application_credentials: str = ""
    firestore_collection: str = "submissions"

    # Firebase Storage bucket for audio (e.g. "my-project.appspot.com" or
    # "my-project.firebasestorage.app"). When set, audio is uploaded there and
    # the frontend plays it from a Firebase download URL. When empty, audio is
    # stored locally and served from /api/audio (dev fallback).
    firebase_storage_bucket: str = ""

    # --- Auth --------------------------------------------------------------
    # Verify the Firebase ID token on every upload. Can be disabled for quick
    # local smoke tests where you don't want to wire up a real token.
    verify_auth: bool = True

    # --- Storage -----------------------------------------------------------
    # Where uploaded audio is persisted locally and the public base URL the
    # frontend uses to play it back. In production both are replaced by a
    # Cloud Storage bucket + signed URLs (see DEPLOYMENT.md).
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
