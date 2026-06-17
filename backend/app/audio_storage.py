"""Where uploaded audio is persisted and how it's served back for playback.

Two implementations behind one interface:

* :class:`FirebaseAudioStorage` — uploads to a Firebase Storage bucket and
  returns a Firebase download URL (token-based, like the client SDK's
  ``getDownloadURL``). This is what lets the frontend play audio online,
  independent of the backend host.
* :class:`LocalAudioStorage` — writes to a local directory and serves via the
  backend's ``/api/audio`` route. Dev fallback when no bucket is configured.

Whisper needs a real file on disk, so every backend also drops a transient local
copy (``transcription_path``) that the pipeline deletes via ``cleanup`` once
transcription is done (a no-op for local storage, where that file *is* what we
serve).
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Protocol
from urllib.parse import quote

from .config import Settings

logger = logging.getLogger(__name__)


class AudioStorage(Protocol):
    def store(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        """Persist the audio and return a playback URL."""

    def transcription_path(self, key: str) -> str:
        """Local path Whisper can read for this key."""

    def cleanup(self, key: str) -> None:
        """Remove any transient local copy."""


class LocalAudioStorage:
    """Writes to a local dir; served by the backend's /api/audio route."""

    def __init__(self, directory: str, public_base_url: str) -> None:
        self._dir = directory
        self._public_base_url = public_base_url.rstrip("/")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self._dir, f"{key}.webm")

    def store(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        with open(self._path(key), "wb") as f:
            f.write(data)
        return f"{self._public_base_url}/api/audio/{key}"

    def transcription_path(self, key: str) -> str:
        return self._path(key)

    def cleanup(self, key: str) -> None:
        # The local file *is* what we serve — keep it.
        return None


class FirebaseAudioStorage:
    """Uploads to a Firebase Storage bucket; returns a token download URL."""

    def __init__(self, bucket_name: str, temp_dir: str) -> None:
        from firebase_admin import storage  # lazy: only when configured

        self._bucket = storage.bucket(bucket_name)
        self._bucket_name = bucket_name
        self._temp_dir = temp_dir
        os.makedirs(self._temp_dir, exist_ok=True)

    def _temp_path(self, key: str) -> str:
        return os.path.join(self._temp_dir, f"{key}.webm")

    def store(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        # Transient local copy for Whisper.
        with open(self._temp_path(key), "wb") as f:
            f.write(data)

        # Upload with a download token so the URL works without public ACLs or
        # signed-URL key material — mirrors what getDownloadURL() returns.
        object_path = f"recordings/{key}.webm"
        token = str(uuid.uuid4())
        blob = self._bucket.blob(object_path)
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.upload_from_string(data, content_type=content_type)

        encoded = quote(object_path, safe="")
        return (
            f"https://firebasestorage.googleapis.com/v0/b/{self._bucket_name}"
            f"/o/{encoded}?alt=media&token={token}"
        )

    def transcription_path(self, key: str) -> str:
        return self._temp_path(key)

    def cleanup(self, key: str) -> None:
        try:
            os.remove(self._temp_path(key))
        except OSError:
            pass


def create_audio_storage(settings: Settings) -> AudioStorage:
    """Use Firebase Storage when a bucket is configured + firebase is live."""
    if settings.firebase_storage_bucket:
        try:
            import firebase_admin

            if firebase_admin._apps:
                storage = FirebaseAudioStorage(
                    settings.firebase_storage_bucket, settings.audio_store_dir
                )
                logger.info(
                    "Using Firebase Storage bucket '%s' for audio.",
                    settings.firebase_storage_bucket,
                )
                return storage
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning(
                "Firebase Storage unavailable (%s); using local audio storage.", exc
            )
    logger.info("Using local audio storage at '%s'.", settings.audio_store_dir)
    return LocalAudioStorage(settings.audio_store_dir, settings.public_base_url)
