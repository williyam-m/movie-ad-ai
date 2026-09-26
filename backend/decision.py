from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from backend.schemas import (
    BoundaryObservation,
    Brand,
    BreakCandidate,
    CandidateFeatures,
    PacingPolicy,
    Scene,
    SpeechSegment,
)

TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def normalise_text(value: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(value.casefold()))


class SimilarityBackend(Protocol):
    @property
    def name(self) -> str: ...

    def similarity(self, left: str, right: str) -> float: ...


class LexicalSimilarity:
    """Deterministic fallback used when the multilingual encoder is unavailable."""

    name = "lexical fail-closed fallback"

    def similarity(self, left: str, right: str) -> float:
        left_normalised = normalise_text(left)
        right_normalised = normalise_text(right)
        if not left_normalised or not right_normalised:
            return 0.0
        if left_normalised in right_normalised or right_normalised in left_normalised:
            return 1.0
        left_tokens = set(left_normalised.split())
        right_tokens = set(right_normalised.split())
        union = left_tokens | right_tokens
        token_score = len(left_tokens & right_tokens) / len(union) if union else 0.0
        sequence_score = SequenceMatcher(
            None, left_normalised, right_normalised
        ).ratio()
        return clamp(max(token_score, sequence_score * 0.55))


@dataclass(frozen=True)
class BrandMatch:
    brand: Brand
    score: float
    reasons: list[str]
    blocked_brand_ids: list[str]


def _maximum_similarity(
    anchors: Sequence[str],
    targets: Sequence[str],
    similarity: SimilarityBackend,
) -> float:
    if not anchors or not targets:
        return 0.0
    return max(
        similarity.similarity(anchor, target)
        for anchor in anchors
        for target in targets
    )


def _negative_context_match(
    brand: Brand,
    scene_texts: Sequence[str],
    similarity: SimilarityBackend,
    threshold: float,
) -> tuple[bool, str | None]:
    for negative_context in brand.negative_contexts:
        for scene_text in scene_texts:
            score = similarity.similarity(negative_context, scene_text)
            if score >= threshold:
                return True, negative_context
    return False, None


def match_brand(
    scene_before: Scene,
    scene_after: Scene,
    brands: Sequence[Brand],
    similarity: SimilarityBackend | None = None,
    negative_threshold: float = 0.72,
    minimum_score: float = 0.5,
) -> BrandMatch | None:
    """Rank arbitrary catalogue entries after hard-eliminating unsafe brands."""

    engine = similarity or LexicalSimilarity()
    scene_texts = [
        *scene_before.contexts,
        *scene_after.contexts,
        scene_before.description,
        scene_after.description,
        scene_before.transcript,
        scene_after.transcript,
        scene_before.mood,
        scene_after.mood,
    ]
    dominant_activity = scene_after.dominant_activity or scene_before.dominant_activity
    supporting_activities = [
        *scene_after.activities,
        scene_before.dominant_activity,
        *scene_before.activities,
    ]
    context_terms = [*scene_after.contexts, *scene_before.contexts]

    blocked_brand_ids: list[str] = []
    ranked: list[tuple[float, Brand, float, float, float]] = []
    for brand in brands:
        is_blocked, _ = _negative_context_match(
            brand, scene_texts, engine, negative_threshold
        )
        if is_blocked:
            blocked_brand_ids.append(brand.id)
            continue

        dominant_score = _maximum_similarity(
            [dominant_activity], brand.target_activities, engine
        )
        activity_score = _maximum_similarity(
            supporting_activities, brand.target_activities, engine
        )
        context_score = _maximum_similarity(
            context_terms, brand.positive_contexts, engine
        )
        total_score = clamp(
            0.68 * dominant_score + 0.20 * activity_score + 0.12 * context_score
        )
        ranked.append(
            (total_score, brand, dominant_score, activity_score, context_score)
        )

    if not ranked:
        return None

    score, brand, dominant_score, activity_score, context_score = max(
        ranked, key=lambda item: (item[0], item[2], item[1].id)
    )
    if score < minimum_score:
        return None
    reasons = [
        f"dominant activity '{dominant_activity}' match {dominant_score:.0%}",
        f"supporting activity match {activity_score:.0%}",
    ]
    if brand.positive_contexts:
        reasons.append(f"positive context match {context_score:.0%}")
    return BrandMatch(
        brand=brand,
        score=round(score, 4),
        reasons=reasons,
        blocked_brand_ids=sorted(blocked_brand_ids),
    )


def score_boundary(
    observation: BoundaryObservation,
    speech_segments: Sequence[SpeechSegment],
    duration: float,
    policy: PacingPolicy,
) -> BreakCandidate:
    guard = policy.dialogue_guard_seconds
    speech_overlap = any(
        segment.start < observation.timestamp + guard
        and segment.end > observation.timestamp - guard
        for segment in speech_segments
    )
    before_margin, after_margin = policy.edge_margins(duration)
    edge_margin = min(observation.timestamp, duration - observation.timestamp)
    required_edge = min(before_margin, after_margin)

    visual_score = clamp(observation.visual_change)
    silence_score = clamp(observation.silence_seconds / 1.2)
    semantic_score = clamp(observation.semantic_shift)
    edge_score = clamp(edge_margin / max(required_edge, 1.0))
    score = clamp(
        0.36 * visual_score
        + 0.34 * silence_score
        + 0.20 * semantic_score
        + 0.10 * edge_score
    )

    hard_blocks: list[str] = []
    reasons: list[str] = []
    if speech_overlap:
        hard_blocks.append("speech overlaps the boundary guard window")
    else:
        reasons.append("no detected speech crosses the boundary")
    if observation.silence_seconds < policy.min_silence_seconds:
        hard_blocks.append(
            f"silence {observation.silence_seconds:.2f}s is below the "
            f"{policy.min_silence_seconds:.2f}s minimum"
        )
    else:
        reasons.append(f"{observation.silence_seconds:.2f}s local silence")
    if observation.timestamp < before_margin:
        hard_blocks.append("too close to programme start")
    if duration - observation.timestamp < after_margin:
        hard_blocks.append("too close to programme end")
    if observation.visual_change >= 0.55:
        reasons.append("strong visual transition")
    if observation.semantic_shift >= 0.55:
        reasons.append("clear semantic scene change")
    if score < policy.min_interruptibility:
        hard_blocks.append(
            f"interruptibility {score:.0%} is below the "
            f"{policy.min_interruptibility:.0%} threshold"
        )

    is_safe = not hard_blocks
    return BreakCandidate(
        id=f"boundary-{round(observation.timestamp * 1000)}",
        timestamp=round(observation.timestamp, 3),
        interruptibility_score=round(score, 4),
        is_safe=is_safe,
        decision="Eligible for pacing" if is_safe else "Rejected: " + hard_blocks[0],
        reasons=[*hard_blocks, *reasons],
        features=CandidateFeatures(
            visual_change=round(visual_score, 4),
            silence_seconds=round(observation.silence_seconds, 3),
            semantic_shift=round(semantic_score, 4),
            speech_overlap=speech_overlap,
            edge_margin=round(max(0.0, edge_margin), 3),
        ),
    )


def select_paced_candidates(
    candidates: Sequence[BreakCandidate],
    duration: float,
    policy: PacingPolicy,
    ad_duration_seconds: float,
) -> list[BreakCandidate]:
    if duration <= 0 or ad_duration_seconds <= 0:
        return []

    rate_limit = max(1, math.ceil(duration / 3600 * policy.max_breaks_per_hour))
    ad_fraction = policy.max_ad_load_percent / 100
    load_limit = math.floor(
        (ad_fraction * duration) / ((1 - ad_fraction) * ad_duration_seconds)
    )
    limit = min(rate_limit, max(0, load_limit))
    if limit == 0:
        return []

    selected: list[BreakCandidate] = []
    for candidate in sorted(
        (item for item in candidates if item.is_safe),
        key=lambda item: (-item.interruptibility_score, item.timestamp),
    ):
        if all(
            abs(candidate.timestamp - existing.timestamp) >= policy.min_gap_seconds
            for existing in selected
        ):
            selected.append(candidate)
        if len(selected) == limit:
            break
    return sorted(selected, key=lambda item: item.timestamp)
