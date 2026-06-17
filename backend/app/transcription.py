"""Whisper transcription with a graceful dev fallback.

The Whisper model is loaded **once** at application startup (see
``main.lifespan``) and reused across requests — loading per request would add
seconds of latency and blow up memory. ``transcribe_file`` is CPU-bound and is
run in a worker thread by the pipeline.

If ``openai-whisper`` (or its native deps) isn't installed, or the model fails
to load, we fall back to :class:`MockTranscriber` so the backend still boots and
the end-to-end flow can be exercised in local dev / via Swagger.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class TranscriberProtocol(Protocol):
    def transcribe_file(self, path: str) -> str: ...


class WhisperTranscriber:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def load(self) -> None:
        """Load the Whisper model into memory. Call once at startup."""
        import whisper  # imported lazily so the app boots without torch

        logger.info("Loading Whisper model '%s'...", self._model_name)
        self._model = whisper.load_model(self._model_name)
        logger.info("Whisper model '%s' ready.", self._model_name)

    def transcribe_file(self, path: str) -> str:
        if self._model is None:
            raise RuntimeError("Whisper model not loaded. Call load() at startup.")
        result = self._model.transcribe(path, fp16=False)
        return str(result.get("text", "")).strip()


class MockTranscriber:
    """Returns placeholder text so the pipeline runs without Whisper installed."""

    def transcribe_file(self, path: str) -> str:  # noqa: ARG002 - signature parity
        logger.warning("Using MockTranscriber — install openai-whisper for real ASR.")
        return "(mock transcription — Whisper not available in this environment)"


def create_transcriber(model_name: str) -> TranscriberProtocol:
    """Build a real Whisper transcriber, falling back to a mock on any failure."""
    transcriber = WhisperTranscriber(model_name)
    try:
        transcriber.load()
        return transcriber
    except Exception as exc:  # noqa: BLE001 - degrade gracefully in dev
        logger.warning("Whisper unavailable (%s); falling back to MockTranscriber.", exc)
        return MockTranscriber()
