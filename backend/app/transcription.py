"""Whisper transcription.

The model is loaded **once** at application startup (see ``main.lifespan``) and
reused across requests — loading per request would add seconds of latency and
blow up memory. ``transcribe_file`` is synchronous/CPU-bound and is therefore
run in a worker thread by the pipeline.
"""
from __future__ import annotations

import logging

import whisper

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def load(self) -> None:
        """Load the Whisper model into memory. Call once at startup."""
        logger.info("Loading Whisper model '%s'...", self._model_name)
        self._model = whisper.load_model(self._model_name)
        logger.info("Whisper model '%s' ready.", self._model_name)

    def transcribe_file(self, path: str) -> str:
        if self._model is None:
            raise RuntimeError("Whisper model not loaded. Call load() at startup.")
        result = self._model.transcribe(path, fp16=False)
        return str(result.get("text", "")).strip()
