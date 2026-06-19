"""Thin wrapper around the Firestore Admin SDK.

The backend is the only writer of pipeline results; the frontend reads the same
documents through the client SDK's real-time listener. Keeping all Firestore
access here keeps the pipeline testable and the field names in one place.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from .config import Settings
from .store import STATUS_DONE, STATUS_ERROR, STATUS_PROCESSING

logger = logging.getLogger(__name__)


class FirestoreClient:
    can_verify_tokens = True

    def __init__(self, settings: Settings) -> None:
        self._collection_name = settings.firestore_collection
        if not firebase_admin._apps:  # idempotent across reloads
            if settings.google_application_credentials:
                cred = credentials.Certificate(settings.google_application_credentials)
                firebase_admin.initialize_app(cred)
            elif settings.google_application_credentials_json:
                # Raw JSON contents — for platforms with no file mounts (e.g.
                # a Hugging Face Space secret holding the service-account key).
                info = json.loads(settings.google_application_credentials_json)
                firebase_admin.initialize_app(credentials.Certificate(info))
            else:
                # Application Default Credentials (Cloud Run, gcloud auth, etc.)
                firebase_admin.initialize_app()
        self._db = firestore.client()

    @property
    def _collection(self):
        return self._db.collection(self._collection_name)

    def create_submission(
        self, *, student_email: str, student_uid: str, audio_url: str
    ) -> str:
        """Create a 'processing' submission and return its document id."""
        doc = self._collection.document()
        doc.set(
            {
                "studentEmail": student_email,
                "studentUid": student_uid,
                "status": STATUS_PROCESSING,
                "audioUrl": audio_url,
                "audioId": audio_url.split("/")[-1],
                "transcription": "",
                "strengths": [],
                "improvements": [],
                # Teacher review (filled in later from the teacher view).
                "reviewStatus": "pending",
                "transcriptVerified": False,
                "teacherNotes": "",
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
        return doc.id

    def mark_done(self, submission_id: str, feedback: dict[str, Any]) -> None:
        self._collection.document(submission_id).update(
            {
                "status": STATUS_DONE,
                "transcription": feedback["transcription"],
                "strengths": feedback["strengths"],
                "improvements": feedback["improvements"],
                "completedAt": firestore.SERVER_TIMESTAMP,
            }
        )

    def mark_error(self, submission_id: str, message: str) -> None:
        self._collection.document(submission_id).update(
            {"status": STATUS_ERROR, "error": message}
        )

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        snap = self._collection.document(submission_id).get()
        if not snap.exists:
            return None
        return {"id": snap.id, **snap.to_dict()}

    def list_submissions(self) -> list[dict[str, Any]]:
        docs = self._collection.order_by(
            "createdAt", direction=firestore.Query.DESCENDING
        ).stream()
        return [{"id": d.id, **d.to_dict()} for d in docs]

    def verify_id_token(self, id_token: str) -> dict[str, Any]:
        from firebase_admin import auth

        return auth.verify_id_token(id_token)
