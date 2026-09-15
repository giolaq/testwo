"""TableStory recipe fixture loader and validator.

Reads the local recipes.json fixture, validates every recipe eagerly, and
returns an immutable collection plus an id index. Pure and offline: the only
input is a local file path, and nothing here reads configuration outside the
arguments it is given.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

ROOT = Path(__file__).parent
FIXTURE_NAME = "recipes.json"

RECIPE_FIELDS = (
    "id",
    "title",
    "description",
    "category",
    "dietary_tags",
    "prep_minutes",
    "cook_minutes",
    "difficulty",
    "servings",
    "ingredients",
    "steps",
    "colors",
    "featured",
)
DIFFICULTIES = ("Easy", "Medium", "Confident Cook")
MIN_STEPS = 3
COLOR_COUNT = 2

URL_SAFE_ID = re.compile(r"^[A-Za-z0-9._~-]+$")
CSS_COLOR = re.compile(
    r"^(?:#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})"
    r"|(?:rgb|rgba|hsl|hsla)\([^()]+\)"
    r"|[a-zA-Z]+)$"
)


class RecipeCollection(NamedTuple):
    """Immutable ordered recipes plus their id index."""

    recipes: tuple[dict, ...]
    by_id: Mapping[str, dict]


def _fail(identifier: str, position: int, field: str, problem: str) -> None:
    raise ValueError(
        f"recipe {identifier!r} (position {position}): field {field!r} {problem}"
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_text_list(value: Any, *, allow_empty: bool) -> bool:
    if not isinstance(value, list):
        return False
    if not value and not allow_empty:
        return False
    return all(isinstance(item, str) and item.strip() for item in value)


def validate_recipe(raw: Any, position: int) -> dict:
    """Return the recipe unchanged, or raise ValueError naming the id and field."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"recipe at position {position}: field 'id' cannot be read because the "
            f"entry is {type(raw).__name__}, not an object"
        )

    identifier = raw.get("id") if isinstance(raw.get("id"), str) else str(position)

    missing = [field for field in RECIPE_FIELDS if field not in raw]
    if missing:
        _fail(identifier, position, missing[0], "is missing")
    unexpected = [field for field in raw if field not in RECIPE_FIELDS]
    if unexpected:
        _fail(identifier, position, sorted(unexpected)[0], "is not a recipe field")

    if not isinstance(raw["id"], str) or not URL_SAFE_ID.match(raw["id"]):
        _fail(identifier, position, "id", "is not a URL-safe identifier")

    for field in ("title", "description", "category", "difficulty"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            _fail(identifier, position, field, "must be a non-empty string")

    if not _is_text_list(raw["dietary_tags"], allow_empty=True):
        _fail(identifier, position, "dietary_tags", "must be a list of non-empty strings")

    if not _is_int(raw["prep_minutes"]) or raw["prep_minutes"] < 1:
        _fail(identifier, position, "prep_minutes", "must be an integer of at least 1")
    if not _is_int(raw["cook_minutes"]) or raw["cook_minutes"] < 0:
        _fail(identifier, position, "cook_minutes", "must be an integer of at least 0")

    if raw["difficulty"] not in DIFFICULTIES:
        _fail(
            identifier,
            position,
            "difficulty",
            f"must be one of {', '.join(DIFFICULTIES)}",
        )

    if not _is_int(raw["servings"]) or raw["servings"] < 1:
        _fail(identifier, position, "servings", "must be an integer of at least 1")

    if not _is_text_list(raw["ingredients"], allow_empty=False):
        _fail(
            identifier,
            position,
            "ingredients",
            "must be a non-empty list of display-ready strings",
        )

    if not _is_text_list(raw["steps"], allow_empty=False) or len(raw["steps"]) < MIN_STEPS:
        _fail(
            identifier,
            position,
            "steps",
            f"must be a list of at least {MIN_STEPS} instruction strings",
        )

    colors = raw["colors"]
    if not isinstance(colors, list) or len(colors) != COLOR_COUNT:
        _fail(
            identifier,
            position,
            "colors",
            f"must contain exactly {COLOR_COUNT} CSS colour values",
        )
    for color in colors:
        if not isinstance(color, str) or not CSS_COLOR.match(color.strip()):
            _fail(identifier, position, "colors", f"contains an invalid CSS colour {color!r}")

    if not isinstance(raw["featured"], bool):
        _fail(identifier, position, "featured", "must be a boolean")

    return raw


def build_collection(recipes: Sequence[dict]) -> RecipeCollection:
    """Freeze the recipes in order and index them by id."""
    by_id: dict[str, dict] = {}
    for position, recipe in enumerate(recipes):
        recipe_id = recipe["id"]
        if recipe_id in by_id:
            _fail(recipe_id, position, "id", "is a duplicate recipe identifier")
        by_id[recipe_id] = recipe
    return RecipeCollection(recipes=tuple(recipes), by_id=by_id)


def load_recipes(path: Path | str | None = None) -> RecipeCollection:
    """Load, validate and freeze the recipe collection from a local JSON file.

    ``path`` exists only as a test seam; production callers pass nothing and the
    fixture next to this module is used.
    """
    source = Path(path) if path is not None else ROOT / FIXTURE_NAME
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{source.name} must contain a JSON array of recipes")
    validated = [validate_recipe(entry, position) for position, entry in enumerate(raw)]
    return build_collection(validated)
