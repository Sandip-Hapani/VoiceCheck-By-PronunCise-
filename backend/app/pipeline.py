"""The async processing pipeline: transcribe -> generate feedback -> persist.

Runs in the background after the upload response has been sent. Each Firestore
write is what drives the frontend's live ``Uploading -> Processing -> Done``
status via its real-time listener.
"""
from __future__ import annotations

import logging

from .config import Settings
from .firestore_client import FirestoreClient
from .llm import generate_feedback
from .transcription import Transcriber

logger = logging.getLogger(__name__)


def process_submission(
    *,
    submission_id: str,
    audio_path: str,
    transcriber: Transcriber,
    firestore: FirestoreClient,
    settings: Settings,
) -> None:
    """Transcribe the audio, generate feedback, and write results to Firestore.

    Designed to be called from a worker thread (it is fully synchronous and
    CPU-bound). Any failure is recorded on the document as ``status: error``
    so the student isn't left staring at a spinner forever.
    """
    try:
        logger.info("[%s] transcribing %s", submission_id, audio_path)
        transcription = transcriber.transcribe_file(audio_path)

        logger.info("[%s] generating feedback", submission_id)
        feedback = generate_feedback(transcription, settings)

        firestore.mark_done(submission_id, feedback.model_dump())
        logger.info("[%s] done", submission_id)
    except Exception as exc:  # noqa: BLE001 - record and surface to the client
        logger.exception("[%s] pipeline failed", submission_id)
        firestore.mark_error(submission_id, str(exc))
