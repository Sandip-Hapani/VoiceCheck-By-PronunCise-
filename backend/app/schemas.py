"""Pydantic models shared across the pipeline.

``Feedback`` is the contract the assignment specifies. We validate the LLM's
raw JSON against it before anything is written to Firestore, so a malformed
model response can never corrupt a submission document.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Feedback(BaseModel):
    """The structured feedback contract returned to the client."""

    transcription: str
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class SubmissionCreated(BaseModel):
    """Response returned immediately after an upload is accepted."""

    id: str
    status: str
