"""Pydantic request/response models."""

from pydantic import BaseModel, Field
from typing import Optional


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=500)
    duration_s: float = Field(40.0, ge=10, le=600)
    genre: Optional[str] = None


class LyricsRequest(BaseModel):
    lyrics: str = Field(..., min_length=3, max_length=5000)
    duration_s: float = Field(40.0, ge=10, le=600)
    genre: Optional[str] = None


class GenerateResponse(BaseModel):
    id: str
    audio_url: str
    meta: dict


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(pro|studio)$")
    provider: str = Field("mock", pattern="^(mock|mpesa|stripe)$")
    phone: Optional[str] = None
