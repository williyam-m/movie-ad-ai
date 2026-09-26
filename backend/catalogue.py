from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.schemas import Brand


class CatalogueError(ValueError):
    pass


BRAND_LIST = TypeAdapter(list[Brand])


def parse_catalogue(raw_data: object) -> list[Brand]:
    try:
        if isinstance(raw_data, dict):
            raw_data = raw_data.get("brands")
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
