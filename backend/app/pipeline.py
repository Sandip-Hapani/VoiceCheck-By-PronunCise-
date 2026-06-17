"""The async processing pipeline: transcribe -> generate feedback -> persist.

Runs in the background after the upload response has been sent. Each Firestore
write is what drives the frontend's live ``Uploading -> Processing -> Done``
status via its real-time listener.
"""
from __future__ import annotations

import logging

from .audio_storage import AudioStorage
from .config import Settings
from .llm import generate_feedback
from .store import SubmissionStore
from .transcription import TranscriberProtocol

logger = logging.getLogger(__name__)


def process_submission(
    *,
    submission_id: str,
    audio_key: str,
    audio_storage: AudioStorage,
    transcriber: TranscriberProtocol,
    firestore: SubmissionStore,
    settings: Settings,
) -> None:
    """Transcribe the audio, generate feedback, and write results to Firestore.

    Designed to be called from a worker thread (it is fully synchronous and
    CPU-bound). Any failure is recorded on the document as ``status: error``
    so the student isn't left staring at a spinner forever. The transient local
    audio copy is removed once we're done with it.
    """
    audio_path = audio_storage.transcription_path(audio_key)
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
    finally:
        audio_storage.cleanup(audio_key)
