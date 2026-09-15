"""The supported TableStory JSON API: exactly six endpoints, nothing else.

Every JSON response the product serves is produced here, so the public surface
can be audited by reading one function. No alias, redirect or compatibility shim
for any removed path is registered anywhere, which is what makes those paths
answer Flask's default 404.
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from cookbook import CookbookStore, UnknownRecipeError
from rails import build_rails
from recipe_data import RecipeCollection
from recipe_search import filter_recipes

RECIPE_NOT_FOUND = "Recipe not found"
MISSING_ID_MESSAGE = "A recipe id is required to save a recipe to My Cookbook."
UNKNOWN_ID_MESSAGE = "No such recipe, so it cannot be saved to My Cookbook."


def register_api(
    app: Flask, collection: RecipeCollection, store: CookbookStore
) -> None:
    """Register the six supported JSON endpoints on the application."""

    @app.get("/api/recipes")
    def recipes_api():
        return jsonify(filter_recipes(collection.recipes, request.args.get("q")))

    @app.get("/api/recipes/<recipe_id>")
    def recipe_api(recipe_id: str):
        recipe = collection.by_id.get(recipe_id)
        if recipe is None:
            return jsonify({"error": RECIPE_NOT_FOUND}), 404
        return jsonify(recipe)

    @app.get("/api/cookbook")
    def cookbook_api():
        return jsonify(store.saved_recipes())

    @app.post("/api/cookbook")
    def add_to_cookbook():
        body = request.get_json(silent=True)
        recipe_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(recipe_id, str) or not recipe_id:
            return jsonify({"error": MISSING_ID_MESSAGE}), 400
        try:
            recipe_ids = store.add(recipe_id)
        except UnknownRecipeError:
            return jsonify({"error": UNKNOWN_ID_MESSAGE}), 400
        return jsonify({"recipe_ids": recipe_ids}), 201

    @app.delete("/api/cookbook/<recipe_id>")
    def remove_from_cookbook(recipe_id: str):
        return jsonify({"recipe_ids": store.remove(recipe_id)})

    @app.get("/api/rails")
    def rails_api():
        rails = build_rails(collection, store.list())
        return jsonify(
            [
                {"name": rail["name"], "recipe_ids": list(rail["recipe_ids"])}
                for rail in rails
            ]
        )
