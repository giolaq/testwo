"""TableStory page routes and the pure context builders behind them.

Two HTML routes only: GET / and GET /recipe/<recipe_id>. The context builders
are pure functions of their arguments so page content can be asserted without
scraping HTML, and so the mobile and TV presentations can later share one set of
derived values.

View-mode seam
--------------
T-TVBROWSE injects view-mode resolution and template selection here: it resolves
the mode from the request, passes the resolved mode through the optional
``view_mode`` argument of the three builders below, and selects the TV templates
instead of BROWSE_TEMPLATE / DETAIL_TEMPLATE. This ticket renders the mobile
templates unconditionally, so ``view_mode`` is accepted and not yet consulted and
every generated href is the plain mobile path.
"""

from __future__ import annotations

from typing import Any, Sequence

from flask import Flask, abort, render_template

from cookbook import CookbookStore
from recipe_data import RecipeCollection
from recipe_search import searchable_text, total_minutes

BROWSE_PATH = "/"
BROWSE_TEMPLATE = "browse.html"
DETAIL_TEMPLATE = "recipe.html"

BRAND_NAME = "TableStory"
TAGLINE = "Good food, clearly told."
HERO_SENTENCE = (
    "Find a dish for everyday cooking, from a ten-minute breakfast to a "
    "slow weekend dinner."
)
SEARCH_PLACEHOLDER = "Search recipes, ingredients or dishes"
EMPTY_STATE = "No recipes found. Try another ingredient or dish."


def cookbook_control_label(title: str, saved: bool) -> str:
    """The recipe-naming accessible label for a My Cookbook control."""
    if saved:
        return f"Remove {title} from My Cookbook"
    return f"Add {title} to My Cookbook"


def detail_href(recipe_id: str, view_mode: Any = None) -> str:
    """The detail path for a recipe. The mobile path is unchanged by view mode."""
    return f"/recipe/{recipe_id}"


def back_href(view_mode: Any = None) -> str:
    """The back target of a detail page: the mobile browse path."""
    return BROWSE_PATH


def card_view(
    recipe: dict, saved_ids: Sequence[str] = (), view_mode: Any = None
) -> dict:
    """The facts one recipe card needs, derived once for every rendering mode."""
    saved = recipe["id"] in set(saved_ids)
    labels = [recipe["category"], *recipe["dietary_tags"]]
    return {
        "recipe": recipe,
        "total_minutes": total_minutes(recipe),
        "difficulty": recipe["difficulty"],
        "label": labels[0],
        "labels": labels,
        "search_text": searchable_text(recipe),
        "saved": saved,
        "control_label": cookbook_control_label(recipe["title"], saved),
        "detail_href": detail_href(recipe["id"], view_mode),
        "artwork_initial": recipe["title"][0].upper(),
        "colors": list(recipe["colors"]),
    }


def browse_context(
    collection: RecipeCollection, store: CookbookStore, view_mode: Any = None
) -> dict:
    """Everything the browse template renders, with one card view per recipe."""
    saved_ids = store.list()
    cards = [card_view(recipe, saved_ids, view_mode) for recipe in collection.recipes]
    return {
        "brand_name": BRAND_NAME,
        "browse_href": BROWSE_PATH,
        "tagline": TAGLINE,
        "hero_sentence": HERO_SENTENCE,
        "search_placeholder": SEARCH_PLACEHOLDER,
        "empty_state": EMPTY_STATE,
        "cards": cards,
        "match_count": len(cards),
    }


def detail_context(
    recipe: dict, store: CookbookStore, view_mode: Any = None
) -> dict:
    """The complete recipe-page context: nine attributes, ordered content, state.

    T-DETAIL renders the metadata block, the ingredient list, the numbered steps
    and the state-bearing save control from these values; this ticket supplies
    them in full and renders the minimal title/description/back page.
    """
    saved = recipe["id"] in store
    return {
        "brand_name": BRAND_NAME,
        "recipe": recipe,
        "title": recipe["title"],
        "description": recipe["description"],
        "category": recipe["category"],
        "dietary_tags": list(recipe["dietary_tags"]),
        "prep_minutes": recipe["prep_minutes"],
        "cook_minutes": recipe["cook_minutes"],
        "total_minutes": total_minutes(recipe),
        "difficulty": recipe["difficulty"],
        "servings": recipe["servings"],
        "ingredients": list(recipe["ingredients"]),
        "steps": list(recipe["steps"]),
        "saved": saved,
        "control_label": cookbook_control_label(recipe["title"], saved),
        "artwork_initial": recipe["title"][0].upper(),
        "colors": list(recipe["colors"]),
        "back_href": back_href(view_mode),
    }


def register_pages(
    app: Flask, collection: RecipeCollection, store: CookbookStore
) -> None:
    """Register the two supported HTML routes on the application."""

    @app.get(BROWSE_PATH)
    def browse():
        return render_template(BROWSE_TEMPLATE, **browse_context(collection, store))

    @app.get("/recipe/<recipe_id>")
    def recipe_page(recipe_id: str):
        recipe = collection.by_id.get(recipe_id)
        if recipe is None:
            abort(404)
        return render_template(DETAIL_TEMPLATE, **detail_context(recipe, store))
