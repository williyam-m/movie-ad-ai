from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.schemas import Brand


class CatalogueError(ValueError):
    pass


BRAND_LIST = TypeAdapter(list[Brand])
LEGACY_BRAND_COLORS = (
    "#D94A3D",
    "#2D8C75",
    "#C05C8A",
    "#3478B8",
    "#B96B32",
    "#4B9B57",
    "#6758A8",
    "#C08B2E",
)


def _legacy_display_name(item: dict[str, object], identifier: str) -> str:
    supplied_name = str(item.get("display_name", "")).strip()
    if supplied_name and re.fullmatch(
        r"brand[\s_-]*[a-z0-9]+", supplied_name, re.I
    ) is None:
        return supplied_name
    categories = [
        category.strip().title()
        for category in str(item.get("category", "")).split("/")
        if category.strip()
    ]
    return " & ".join(categories[:2]) or identifier.replace("-", " ").title()


def _adapt_legacy_catalogue(raw_data: object) -> object:
    if not isinstance(raw_data, list) or not raw_data:
        return raw_data
    if not all(isinstance(item, dict) and "brand_id" in item for item in raw_data):
        return raw_data

    adapted: list[dict[str, object]] = []
    for index, item in enumerate(raw_data):
        identifier = re.sub(
            r"[^a-z0-9-]+", "-", str(item["brand_id"]).strip().casefold()
        ).strip("-")
        category = str(item.get("category", "general")).split("/", 1)[0].strip()
        target_contexts = item.get("target_contexts", [])
        creatives = item.get("creatives", [])
        durations = [
            creative.get("duration_sec")
            for creative in creatives
            if isinstance(creative, dict)
            and isinstance(creative.get("duration_sec"), int | float)
        ] if isinstance(creatives, list) else []
        adapted.append(
            {
                "id": identifier,
                "name": _legacy_display_name(item, identifier),
                "category": category,
                "description": (
                    f"Contextual {category} creative for the supplied demo catalogue."
                ),
                "tagline": "Made for the moment.",
                "color": LEGACY_BRAND_COLORS[index % len(LEGACY_BRAND_COLORS)],
                "target_activities": target_contexts,
                "positive_contexts": target_contexts,
                "negative_contexts": item.get("negative_contexts", []),
                "creative_path": f"/media/ads/{identifier}.mp4",
                "duration_seconds": min(durations, default=15),
            }
        )
    return adapted


def parse_catalogue(raw_data: object) -> list[Brand]:
    try:
        if isinstance(raw_data, dict):
            raw_data = raw_data.get("brands")
        raw_data = _adapt_legacy_catalogue(raw_data)
        brands = BRAND_LIST.validate_python(raw_data)
    except (ValidationError, TypeError) as error:
        raise CatalogueError(f"Invalid brand catalogue: {error}") from error

    if not brands:
        raise CatalogueError("Brand catalogue must contain at least one entry")
    identifiers = [brand.id for brand in brands]
    if len(identifiers) != len(set(identifiers)):
        raise CatalogueError("Brand catalogue IDs must be unique")
    return brands


def parse_catalogue_bytes(content: bytes) -> list[Brand]:
    try:
        raw_data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CatalogueError(f"Invalid brand catalogue JSON: {error}") from error
    return parse_catalogue(raw_data)


def load_catalogue(path: Path) -> list[Brand]:
    try:
        return parse_catalogue_bytes(path.read_bytes())
    except OSError as error:
        raise CatalogueError(f"Unable to read brand catalogue: {error}") from error
