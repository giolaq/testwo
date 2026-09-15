"""Curated rail composition for the TV browse layout and the rails endpoint.

Pure functions of their arguments: no global state, no Flask, no request access,
so the same composition can serve the TV templates and GET /api/rails later.
Membership is derived from the recipe data rather than hand-listed.
"""

from __future__ import annotations

from typing import Callable, Sequence

from recipe_data import RecipeCollection
from recipe_search import total_minutes

POPULAR_RAIL_NAME = "Popular this week"
QUICK_RAIL_NAME = "Ready in 30 minutes"
VEGETARIAN_RAIL_NAME = "Vegetarian favourites"
COOKBOOK_RAIL_NAME = "My Cookbook"

RAIL_NAMES = (
    POPULAR_RAIL_NAME,
    QUICK_RAIL_NAME,
    VEGETARIAN_RAIL_NAME,
    COOKBOOK_RAIL_NAME,
)

QUICK_MINUTES = 30
VEGETARIAN_TAG = "Vegetarian"

COOKBOOK_EMPTY_STATE = "No saved recipes yet. Add a dish to My Cookbook to see it here."

# The three derived membership predicates. Each is defined once here and passed
# to rail_members, so a rail's membership can never drift from the recipe data.
def IS_POPULAR(recipe: dict) -> bool:
    """'Popular this week' membership: the recipe is featured."""
    return bool(recipe["featured"])


def IS_QUICK(recipe: dict) -> bool:
    """'Ready in 30 minutes' membership: total time is at most QUICK_MINUTES."""
    return total_minutes(recipe) <= QUICK_MINUTES


def IS_VEGETARIAN(recipe: dict) -> bool:
    """'Vegetarian favourites' membership: the Vegetarian dietary tag is present."""
    return VEGETARIAN_TAG in recipe["dietary_tags"]


def rail_members(
    collection: RecipeCollection, predicate: Callable[[dict], bool]
) -> list[dict]:
    """Recipes satisfying the predicate, in collection order."""
    return [recipe for recipe in collection.recipes if predicate(recipe)]


def _rail(name: str, recipes: Sequence[dict]) -> dict:
    return {
        "name": name,
        "recipe_ids": [recipe["id"] for recipe in recipes],
        "recipes": list(recipes),
    }


def cookbook_rail(collection: RecipeCollection, saved_ids: Sequence[str]) -> dict:
    """The My Cookbook rail in saved order, skipping ids no longer present."""
    by_id = collection.by_id
    recipes = [by_id[recipe_id] for recipe_id in saved_ids if recipe_id in by_id]
    rail = _rail(COOKBOOK_RAIL_NAME, recipes)
    rail["empty_state"] = COOKBOOK_EMPTY_STATE
    return rail


def build_rails(
    collection: RecipeCollection, saved_ids: Sequence[str]
) -> list[dict]:
    """Exactly four rails in the fixed order, composed from the recipe data."""
    return [
        _rail(POPULAR_RAIL_NAME, rail_members(collection, IS_POPULAR)),
        _rail(QUICK_RAIL_NAME, rail_members(collection, IS_QUICK)),
        _rail(VEGETARIAN_RAIL_NAME, rail_members(collection, IS_VEGETARIAN)),
        cookbook_rail(collection, list(saved_ids)),
    ]
