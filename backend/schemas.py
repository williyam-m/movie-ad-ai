from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Brand(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=500)
    tagline: str = Field(min_length=2, max_length=120)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    target_activities: list[str] = Field(min_length=1, max_length=30)
    positive_contexts: list[str] = Field(default_factory=list, max_length=30)
    negative_contexts: list[str] = Field(min_length=1, max_length=40)
    creative_path: str = Field(min_length=1, max_length=240)
    duration_seconds: float = Field(default=6.0, ge=1.0, le=120.0)

    @field_validator("creative_path")
    @classmethod
    def validate_creative_path(cls, value: str) -> str:
        parsed = urlparse(value)
        if value.startswith("/media/") or parsed.scheme == "https":
            return value
        raise ValueError("creative_path must be a /media path or an HTTPS URL")

    @field_validator("target_activities", "positive_contexts", "negative_contexts")
    @classmethod
    def normalise_terms(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().lower() for value in values if value.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("context terms must be unique")
        return cleaned


class BrandSummary(StrictModel):
    id: str
    name: str
    category: str
    tagline: str
    color: str


class SpeechSegment(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = ""


class Scene(StrictModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    duration: float = Field(gt=0)
    visual_score: float = Field(ge=0, le=1)
    dominant_activity: str
    activities: list[str]
    contexts: list[str]
    mood: str
    description: str
    transcript: str = ""


class BoundaryObservation(StrictModel):
    timestamp: float = Field(gt=0)
    visual_change: float = Field(ge=0, le=1)
    silence_seconds: float = Field(ge=0)
    semantic_shift: float = Field(ge=0, le=1)


class CandidateFeatures(StrictModel):
    visual_change: float = Field(ge=0, le=1)
    silence_seconds: float = Field(ge=0)
    semantic_shift: float = Field(ge=0, le=1)
    speech_overlap: bool
    edge_margin: float = Field(ge=0)


class BreakCandidate(StrictModel):
    id: str
    timestamp: float
    interruptibility_score: float = Field(ge=0, le=1)
    is_safe: bool
    decision: str
    reasons: list[str]
    features: CandidateFeatures


class BreakSlot(StrictModel):
    id: str
    timestamp: float
    time_offset: str
    score: float = Field(ge=0, le=1)
    scene_id: str
    brand: BrandSummary
    creative_url: str
    duration: float
    match_score: float = Field(ge=0, le=1)
    why: list[str]
    blocked_brands: list[str]


class PacingPolicy(StrictModel):
    max_breaks_per_hour: int = Field(default=4, ge=1, le=12)
    min_gap_seconds: float = Field(default=420, ge=30, le=1800)
    max_ad_load_percent: float = Field(default=8, ge=1, le=20)
    min_interruptibility: float = Field(default=0.62, ge=0.4, le=0.95)
    min_silence_seconds: float = Field(default=0.35, ge=0.1, le=2.0)
    dialogue_guard_seconds: float = Field(default=0.45, ge=0.1, le=2.0)
    min_content_before_seconds: float = Field(default=120, ge=0, le=900)
    min_content_after_seconds: float = Field(default=120, ge=0, le=900)

    def edge_margins(self, duration: float) -> tuple[float, float]:
        short_form_margin = max(8.0, duration * 0.08)
        return (
            min(self.min_content_before_seconds, short_form_margin),
            min(self.min_content_after_seconds, short_form_margin),
        )


class AnalysisSummary(StrictModel):
    scene_count: int
    candidate_count: int
    safe_candidate_count: int
    break_count: int
    ad_load_percent: float


class ModelReport(StrictModel):
    visual: str
    speech: str
    semantics: str
    degraded: bool
    notes: list[str]


class AnalysisResult(StrictModel):
    job_id: str
    source_name: str
    duration_seconds: float
    media_url: str
    generated_at: datetime
    summary: AnalysisSummary
    policy: PacingPolicy
    models: ModelReport
    scenes: list[Scene]
    candidates: list[BreakCandidate]
    breaks: list[BreakSlot]
    manifest_url: str
    debug_url: str


class JobRecord(StrictModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: str
    progress: float = Field(ge=0, le=1)
    error: str | None = None
    result: AnalysisResult | None = None


class DemoRequest(StrictModel):
    max_breaks_per_hour: int = Field(default=4, ge=1, le=12)
    min_gap_seconds: float = Field(default=420, ge=30, le=1800)
    max_ad_load_percent: float = Field(default=8, ge=1, le=20)
