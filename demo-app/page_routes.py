"""TableStory page routes and the pure context builders behind them.

Two HTML routes only: GET / and GET /recipe/<recipe_id>. The context builders
are pure functions of their arguments so page content can be asserted without
scraping HTML, and so the mobile and TV presentations can later share one set of
derived values.

View-mode seam
--------------
Both routes resolve the view mode through the single resolver in view_mode.py and
build every in-app href through ``mode_url``, so TV mode is retained across
navigation from one implementation. GET / selects the TV rails template when the
resolved mode is TV.

The detail route still renders the mobile detail template in both modes:
T-TVDETAIL owns TV detail template selection, so no intermediate state points at
a template that does not exist yet.
"""

from __future__ import annotations

from typing import Any, Sequence

from flask import Flask, abort, render_template, request

from cookbook import CookbookStore
from rails import build_rails
from recipe_data import RecipeCollection
from recipe_search import searchable_text, total_minutes
from view_mode import QUERY_KEY, is_tv, mode_url, resolve_view_mode

BROWSE_PATH = "/"
BROWSE_TEMPLATE = "browse.html"
TV_BROWSE_TEMPLATE = "tv_browse.html"
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
    """The detail path for a recipe, retaining TV mode when the mode is TV."""
    return mode_url(f"/recipe/{recipe_id}", view_mode)


def back_href(view_mode: Any = None) -> str:
    """The back target of a detail page: the browse path in the current mode."""
    return mode_url(BROWSE_PATH, view_mode)


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
        "browse_href": mode_url(BROWSE_PATH, view_mode),
        "tagline": TAGLINE,
        "hero_sentence": HERO_SENTENCE,
        "search_placeholder": SEARCH_PLACEHOLDER,
        "empty_state": EMPTY_STATE,
        "cards": cards,
        "match_count": len(cards),
    }


def tv_browse_context(
    collection: RecipeCollection, store: CookbookStore, view_mode: Any = None
) -> dict:
    """Everything the TV rails template renders: four rails of card views.

    The rails come from the shared composer, recomposed per request from the
    current cookbook, so a refresh always reflects the saved collection. Each
    rail carries its card views in rail order plus the rail's empty-state copy.
    """
    saved_ids = store.list()
    rails = []
    for rail in build_rails(collection, saved_ids):
        rails.append(
            {
                "name": rail["name"],
                "empty_state": rail.get("empty_state"),
                "cards": [
                    card_view(recipe, saved_ids, view_mode)
                    for recipe in rail["recipes"]
                ],
            }
        )
    return {
        "brand_name": BRAND_NAME,
        "browse_href": mode_url(BROWSE_PATH, view_mode),
        "tagline": TAGLINE,
        "rails": rails,
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

    def current_view_mode() -> dict:
        return resolve_view_mode(
            request.args.get(QUERY_KEY), request.headers.get("User-Agent")
        )

    @app.get(BROWSE_PATH)
    def browse():
        view_mode = current_view_mode()
        if is_tv(view_mode):
            return render_template(
                TV_BROWSE_TEMPLATE,
                **tv_browse_context(collection, store, view_mode),
            )
        return render_template(
            BROWSE_TEMPLATE, **browse_context(collection, store, view_mode)
        )

    @app.get("/recipe/<recipe_id>")
    def recipe_page(recipe_id: str):
        recipe = collection.by_id.get(recipe_id)
        if recipe is None:
            abort(404)
        # The mobile detail template serves both modes for now; T-TVDETAIL owns
        # TV detail template selection.
        return render_template(
            DETAIL_TEMPLATE, **detail_context(recipe, store, current_view_mode())
        )
