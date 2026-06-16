"""Feedback generation via a local Ollama model.

We ask the model for strict JSON (Ollama's ``format: json`` mode) and validate
it against :class:`~app.schemas.Feedback`. If Ollama is unreachable or returns
something unusable, we fall back to deterministic mock feedback so the app
remains fully runnable without a local model.
"""
from __future__ import annotations

import json
import logging

import httpx

from .config import Settings
from .schemas import Feedback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a friendly, encouraging pronunciation and speaking coach. "
    "You are given a transcription of a short spoken recording by a language "
    "learner. Give concise, specific, actionable feedback. "
    "Respond ONLY with a JSON object matching this schema: "
    '{"transcription": string, "strengths": string[], "improvements": string[]}. '
    "Echo the transcription back unchanged in the transcription field. "
    "Provide 2-4 strengths and 2-4 improvements. Keep each point to one sentence."
)


def _build_prompt(transcription: str) -> str:
    return (
        f'Here is the transcription of the recording:\n\n"{transcription}"\n\n'
        "Generate the feedback JSON now."
    )


def generate_feedback(transcription: str, settings: Settings) -> Feedback:
    """Return validated :class:`Feedback`, using Ollama with a mock fallback."""
    try:
        return _generate_with_ollama(transcription, settings)
    except Exception as exc:  # noqa: BLE001 - any failure should degrade gracefully
        logger.warning("Ollama feedback failed (%s); using mock fallback.", exc)
        return _mock_feedback(transcription)


def _generate_with_ollama(transcription: str, settings: Settings) -> Feedback:
    payload = {
        "model": settings.ollama_model,
        "format": "json",
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(transcription)},
        ],
    }
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        timeout=settings.llm_timeout_seconds,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    data = json.loads(content)

    # Trust our own transcription over whatever the model echoes back.
    data["transcription"] = transcription
    return Feedback.model_validate(data)


def _mock_feedback(transcription: str) -> Feedback:
    """Deterministic placeholder so the pipeline works without a live model."""
    spoke_something = bool(transcription.strip())
    return Feedback(
        transcription=transcription,
        strengths=(
            ["Clear, steady pace.", "Good overall intonation."]
            if spoke_something
            else ["Recording received."]
        ),
        improvements=[
            "Enunciate word endings more crisply.",
            "Add short pauses between clauses for clarity.",
        ],
    )
