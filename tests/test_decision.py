from backend.decision import (
    LexicalSimilarity,
    match_brand,
    score_boundary,
    select_paced_candidates,
)
from backend.schemas import (
    BoundaryObservation,
    Brand,
    BreakCandidate,
    CandidateFeatures,
    PacingPolicy,
    Scene,
    SpeechSegment,
)


def make_scene(
    scene_id: str,
    activity: str,
    contexts: list[str],
    start: float = 0,
    end: float = 60,
) -> Scene:
    return Scene(
        id=scene_id,
        start=start,
        end=end,
        duration=end - start,
        visual_score=0.8,
        dominant_activity=activity,
        activities=[activity],
        contexts=contexts,
        mood="calm",
        description=f"A scene about {activity} in {' '.join(contexts)}",
        transcript="",
    )


def make_brand(
    brand_id: str,
    category: str,
    target: str,
    negatives: list[str],
) -> Brand:
    return Brand(
        id=brand_id,
        name=brand_id.replace("-", " ").title(),
        category=category,
        description=f"Synthetic {category} brand",
        tagline="Made for this moment",
        color="#CC3344",
        target_activities=[target],
        positive_contexts=[target],
        negative_contexts=negatives,
        creative_path=f"/media/ads/{brand_id}.mp4",
        duration_seconds=6,
    )


def test_mid_dialogue_is_a_hard_rejection_even_with_strong_visuals() -> None:
    candidate = score_boundary(
        BoundaryObservation(
            timestamp=300,
            visual_change=1,
            silence_seconds=1.2,
            semantic_shift=1,
        ),
        [SpeechSegment(start=298, end=302, text="unfinished sentence")],
        duration=1800,
        policy=PacingPolicy(),
    )

    assert candidate.is_safe is False
    assert candidate.features.speech_overlap is True
    assert "speech overlaps" in candidate.decision


def test_missing_silence_fails_closed_when_asr_has_no_overlap() -> None:
    candidate = score_boundary(
        BoundaryObservation(
            timestamp=300,
            visual_change=1,
            silence_seconds=0.1,
            semantic_shift=1,
        ),
        [],
        duration=1800,
        policy=PacingPolicy(),
    )

    assert candidate.is_safe is False
    assert any("silence" in reason for reason in candidate.reasons)


def test_negative_context_removes_brand_before_ranking() -> None:
    funeral = make_scene("s1", "family gathering", ["funeral", "grief"])
    quiet_room = make_scene("s2", "quiet conversation", ["grief"], 60, 120)
    food = make_brand("meal-brand", "food", "family gathering", ["funeral"])
    support = make_brand(
        "support-brand", "wellbeing", "quiet conversation", ["celebration"]
    )

    match = match_brand(funeral, quiet_room, [food, support], LexicalSimilarity())

    assert match is not None
    assert match.brand.id == "support-brand"
    assert "meal-brand" in match.blocked_brand_ids


def test_all_negative_context_matches_return_no_ad() -> None:
    emergency = make_scene("s1", "hospital visit", ["medical emergency"])
    aftermath = make_scene("s2", "waiting", ["hospital"], 60, 120)
    brands = [
        make_brand("food-a", "food", "waiting", ["medical emergency"]),
        make_brand("travel-a", "travel", "waiting", ["hospital"]),
    ]

    assert match_brand(emergency, aftermath, brands) is None


def test_weak_context_does_not_force_an_unrelated_ad() -> None:
    before = make_scene("s1", "police interview", ["station"])
    after = make_scene("s2", "investigation", ["corridor"], 60, 120)
    food = make_brand("meal-brand", "food", "cooking", ["funeral"])

    assert match_brand(before, after, [food], LexicalSimilarity()) is None


def test_unseen_ninth_brand_can_win_from_catalogue_data_only() -> None:
    before = make_scene("s1", "reading", ["home"])
    after = make_scene("s2", "stargazing", ["night sky"], 60, 120)
    existing = [
        make_brand(f"brand-{index}", "general", f"activity {index}", ["danger"])
        for index in range(8)
    ]
    unseen = make_brand("brand-nine", "optics", "stargazing", ["funeral"])

    match = match_brand(before, after, [*existing, unseen])

    assert match is not None
    assert match.brand.id == "brand-nine"
    assert match.score >= 0.68


def test_pacing_enforces_gap_rate_and_ad_load() -> None:
    def candidate(timestamp: float, score: float) -> BreakCandidate:
        return BreakCandidate(
            id=f"b-{timestamp}",
            timestamp=timestamp,
            interruptibility_score=score,
            is_safe=True,
            decision="Eligible for pacing",
            reasons=[],
            features=CandidateFeatures(
                visual_change=1,
                silence_seconds=1,
                semantic_shift=1,
                speech_overlap=False,
                edge_margin=timestamp,
            ),
        )

    selected = select_paced_candidates(
        [candidate(300, 0.9), candidate(500, 0.95), candidate(1000, 0.8)],
        duration=1800,
        policy=PacingPolicy(max_breaks_per_hour=4, min_gap_seconds=420),
        ad_duration_seconds=15,
    )

    assert [item.timestamp for item in selected] == [500, 1000]
