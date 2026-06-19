"""Feedback generation via Groq (hosted) or a local Ollama model (offline dev).

We ask the model for strict JSON and validate it against
:class:`~app.schemas.Feedback`. If the configured provider is unreachable or
returns something unusable, we fall back to deterministic mock feedback so the
app remains fully runnable without any live model.
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
    """Return validated :class:`Feedback`, using Groq/Ollama with a mock fallback.

    Groq is used when ``GROQ_API_KEY`` is set (the hosted path — no local GPU
    needed). Otherwise we talk to local Ollama (the offline dev path).
    """
    provider = "Groq" if settings.groq_api_key else "Ollama"
    try:
        logger.info("Generating feedback with %s.", provider)
        if provider == "Groq":
            return _generate_with_groq(transcription, settings)
        return _generate_with_ollama(transcription, settings)
    except Exception as exc:  # noqa: BLE001 - any failure should degrade gracefully
        logger.warning("%s feedback failed (%s); using mock fallback.", provider, exc)
        return _mock_feedback(transcription)


def _generate_with_groq(transcription: str, settings: Settings) -> Feedback:
    from groq import Groq  # lazy: only needed when GROQ_API_KEY is set

    client = Groq(api_key=settings.groq_api_key)
    resp = client.chat.completions.create(
        model=settings.groq_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(transcription)},
        ],
        timeout=settings.llm_timeout_seconds,
    )
    data = json.loads(resp.choices[0].message.content)

    # Trust our own transcription over whatever the model echoes back.
    data["transcription"] = transcription
    return Feedback.model_validate(data)


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
