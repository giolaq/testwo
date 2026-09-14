"""TableStory recipe search and derived-value helpers.

The single server-side definition of query normalisation, the searchable text of
a recipe, the match predicate, collection filtering and total time. Pure
functions only, so they can be exercised without a web framework or a request.
"""

from __future__ import annotations

from typing import Any, Sequence

SEARCHABLE_FIELDS = ("title", "description", "category", "dietary_tags", "ingredients")


def normalise_query(raw: Any) -> str:
    """Trim and case-fold the query; a non-string degrades to 'match everything'."""
    if not isinstance(raw, str):
        return ""
    return raw.strip().casefold()


def searchable_text(recipe: dict) -> str:
    """Case-folded concatenation of the five searchable recipe fields."""
    parts: list[str] = []
    for field in SEARCHABLE_FIELDS:
        value = recipe.get(field)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def recipe_matches(recipe: dict, raw_query: Any) -> bool:
    """True when the normalised query is a substring of the recipe's searchable text."""
    query = normalise_query(raw_query)
    if not query:
        return True
    return query in searchable_text(recipe)


def filter_recipes(recipes: Sequence[dict], raw_query: Any) -> list[dict]:
    """Matching recipes in collection order; an empty query returns them all."""
    return [recipe for recipe in recipes if recipe_matches(recipe, raw_query)]


def total_minutes(recipe: dict) -> int:
    """Total time for a recipe: prep_minutes + cook_minutes, correct when cook is 0."""
    return recipe["prep_minutes"] + recipe["cook_minutes"]
