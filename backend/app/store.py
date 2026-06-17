"""Submission persistence: a Firestore-backed store with an in-memory fallback.

The backend is the only writer of pipeline results. In production this is
Firestore (the frontend reads the same docs via its real-time listener). For
local dev without Firebase credentials, :class:`InMemoryStore` lets the whole
API run and be exercised through Swagger — there's no real-time listener then,
but the ``GET`` endpoints return the same shape.
"""
from __future__ import annotations

import itertools
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from .config import Settings

logger = logging.getLogger(__name__)

# Document status values, mirrored in the frontend's Submission type.
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"


@runtime_checkable
class SubmissionStore(Protocol):
    """Interface shared by the Firestore and in-memory implementations."""

    can_verify_tokens: bool

    def create_submission(
        self, *, student_email: str, student_uid: str, audio_url: str
    ) -> str: ...
    def mark_done(self, submission_id: str, feedback: dict[str, Any]) -> None: ...
    def mark_error(self, submission_id: str, message: str) -> None: ...
    def get_submission(self, submission_id: str) -> dict[str, Any] | None: ...
    def list_submissions(self) -> list[dict[str, Any]]: ...
    def verify_id_token(self, id_token: str) -> dict[str, Any]: ...


class InMemoryStore:
    """Thread-safe dict-backed store for local dev. Not persistent."""

    can_verify_tokens = False

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def create_submission(
        self, *, student_email: str, student_uid: str, audio_url: str
    ) -> str:
        with self._lock:
            sid = f"mem{next(self._ids):06d}"
            self._docs[sid] = {
                "id": sid,
                "studentEmail": student_email,
                "studentUid": student_uid,
                "status": STATUS_PROCESSING,
                "audioUrl": audio_url,
                "transcription": "",
                "strengths": [],
                "improvements": [],
                "reviewStatus": "pending",
                "transcriptVerified": False,
                "teacherNotes": "",
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
            return sid

    def mark_done(self, submission_id: str, feedback: dict[str, Any]) -> None:
        with self._lock:
            self._docs[submission_id].update(
                {
                    "status": STATUS_DONE,
                    "transcription": feedback["transcription"],
                    "strengths": feedback["strengths"],
                    "improvements": feedback["improvements"],
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                }
            )

    def mark_error(self, submission_id: str, message: str) -> None:
        with self._lock:
            self._docs[submission_id].update({"status": STATUS_ERROR, "error": message})

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        return self._docs.get(submission_id)

    def list_submissions(self) -> list[dict[str, Any]]:
        return sorted(
            self._docs.values(), key=lambda d: d.get("createdAt", ""), reverse=True
        )

    def verify_id_token(self, id_token: str) -> dict[str, Any]:
        raise RuntimeError("InMemoryStore cannot verify Firebase tokens")


def create_store(settings: Settings) -> SubmissionStore:
    """Build a Firestore store, falling back to in-memory if it can't init."""
    try:
        from .firestore_client import FirestoreClient

        store = FirestoreClient(settings)
        logger.info("Using Firestore store.")
        return store
    except Exception as exc:  # noqa: BLE001 - degrade gracefully in dev
        logger.warning(
            "Firestore unavailable (%s); falling back to InMemoryStore. "
            "The frontend real-time listener needs real Firestore.",
            exc,
        )
        return InMemoryStore()
