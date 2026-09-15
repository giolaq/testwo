"""In-memory My Cookbook store.

Holds the saved recipe ids for the life of one application object: process-local
memory only, no storage dependency, no persistence, so the saved collection
resets with the process (R27). One store per application keeps callers isolated.
"""

from __future__ import annotations

from typing import Iterator

from recipe_data import RecipeCollection


class UnknownRecipeError(LookupError):
    """Raised when a saved id is absent from the recipe collection."""


class CookbookStore:
    """Insertion-ordered saved-recipe ids for one application instance."""

    def __init__(self, collection: RecipeCollection) -> None:
        self._collection = collection
        self._saved: dict[str, None] = {}

    def __contains__(self, recipe_id: object) -> bool:
        return recipe_id in self._saved

    def __iter__(self) -> Iterator[str]:
        return iter(tuple(self._saved))

    def __len__(self) -> int:
        return len(self._saved)

    def list(self) -> list[str]:
        """Saved ids in insertion order, as a copy the caller may mutate freely."""
        return list(self._saved)

    def add(self, recipe_id: str) -> list[str]:
        """Save a recipe; re-adding an already-saved id is a successful no-op.

        Raises UnknownRecipeError when the id is absent from the collection, so
        the caller can answer with recipe-domain wording.
        """
        if recipe_id not in self._collection.by_id:
            raise UnknownRecipeError(f"No recipe with id {recipe_id!r}")
        self._saved.setdefault(recipe_id, None)
        return self.list()

    def remove(self, recipe_id: str) -> list[str]:
        """Remove a saved recipe. Idempotent: an absent or unknown id succeeds."""
        self._saved.pop(recipe_id, None)
        return self.list()

    def saved_recipes(self) -> list[dict]:
        """Complete recipe objects in saved order, skipping ids no longer present."""
        by_id = self._collection.by_id
        return [by_id[recipe_id] for recipe_id in self.list() if recipe_id in by_id]
