"""Ticket #1 implementation tests: recipe fixture, loader and search helpers."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from recipe_data import (
    DIFFICULTIES,
    RECIPE_FIELDS,
    build_collection,
    load_recipes,
    validate_recipe,
)
from recipe_search import (
    filter_recipes,
    normalise_query,
    recipe_matches,
    searchable_text,
    total_minutes,
)

DEMO_APP = Path(__file__).parents[1]

BASE_RECIPE = {
    "id": "test-frittata",
    "title": "Test Frittata",
    "description": "A small frittata used only by the loader tests.",
    "category": "Breakfast",
    "dietary_tags": ["Vegetarian"],
    "prep_minutes": 5,
    "cook_minutes": 8,
    "difficulty": "Easy",
    "servings": 2,
    "ingredients": ["4 eggs", "1 courgette", "1 tbsp olive oil"],
    "steps": ["Beat the eggs.", "Fry the courgette.", "Set the frittata under the grill."],
    "colors": ["#E9B44C", "#3F6B4F"],
    "featured": False,
}


@pytest.fixture()
def collection():
    return load_recipes()


def _variant(**changes):
    recipe = copy.deepcopy(BASE_RECIPE)
    for key, value in changes.items():
        recipe[key] = value
    return recipe


def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "recipes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# fixture loading, ordering and the id index
# --------------------------------------------------------------------------- #
def test_fixture_loads_at_least_twelve_recipes_in_file_order(collection):
    raw = json.loads((DEMO_APP / "recipes.json").read_text(encoding="utf-8"))
    assert len(collection.recipes) >= 12
    assert [r["id"] for r in collection.recipes] == [r["id"] for r in raw]
    assert isinstance(collection.recipes, tuple)


def test_id_index_resolves_every_recipe(collection):
    assert set(collection.by_id) == {r["id"] for r in collection.recipes}
    for recipe in collection.recipes:
        assert collection.by_id[recipe["id"]] is recipe


def test_repeated_loads_are_byte_stable():
    first = load_recipes()
    second = load_recipes()
    assert [r["id"] for r in first.recipes] == [r["id"] for r in second.recipes]
    assert list(first.recipes) == list(second.recipes)


# --------------------------------------------------------------------------- #
# per-recipe field rules and the content mix
# --------------------------------------------------------------------------- #
def test_every_recipe_carries_exactly_the_thirteen_fields(collection):
    for recipe in collection.recipes:
        assert tuple(sorted(recipe)) == tuple(sorted(RECIPE_FIELDS)), recipe["id"]
        assert recipe["difficulty"] in DIFFICULTIES, recipe["id"]
        assert recipe["prep_minutes"] >= 1, recipe["id"]
        assert recipe["cook_minutes"] >= 0, recipe["id"]
        assert recipe["servings"] >= 1, recipe["id"]
        assert recipe["ingredients"], recipe["id"]
        assert len(recipe["steps"]) >= 3, recipe["id"]
        assert len(recipe["colors"]) == 2, recipe["id"]
        assert isinstance(recipe["featured"], bool), recipe["id"]


def test_content_mix_meets_every_threshold(collection):
    recipes = collection.recipes
    counts = {
        "recipes": len(recipes),
        "vegetarian": sum(1 for r in recipes if "Vegetarian" in r["dietary_tags"]),
        "vegan": sum(1 for r in recipes if "Vegan" in r["dietary_tags"]),
        "total_time_30_or_less": sum(1 for r in recipes if total_minutes(r) <= 30),
        "dessert": sum(1 for r in recipes if r["category"] == "Dessert"),
        "featured": sum(1 for r in recipes if r["featured"]),
    }
    print(
        "content mix: "
        + " ".join(f"{name}={value}" for name, value in counts.items())
    )
    assert counts["recipes"] >= 12, counts
    assert counts["vegetarian"] >= 3, counts
    assert counts["vegan"] >= 2, counts
    assert counts["total_time_30_or_less"] >= 3, counts
    assert counts["dessert"] >= 2, counts
    assert counts["featured"] >= 2, counts


def test_meal_use_cases_are_covered(collection):
    categories = {r["category"] for r in collection.recipes}
    assert {"Breakfast", "Lunch", "Dinner", "Dessert"} <= categories, categories


def test_every_recipe_is_unique(collection):
    for field in ("id", "title", "description"):
        values = [r[field] for r in collection.recipes]
        assert len(set(values)) == len(values), field
    steps = ["\n".join(r["steps"]) for r in collection.recipes]
    assert len(set(steps)) == len(steps)


# --------------------------------------------------------------------------- #
# malformed fixtures through the injected path
# --------------------------------------------------------------------------- #
def test_injected_fixture_path_loads_only_the_given_recipes(tmp_path):
    loaded = load_recipes(_write(tmp_path, [copy.deepcopy(BASE_RECIPE)]))
    assert [r["id"] for r in loaded.recipes] == ["test-frittata"]


@pytest.mark.parametrize(
    ("recipe", "field"),
    [
        ({k: v for k, v in BASE_RECIPE.items() if k != "ingredients"}, "ingredients"),
        (_variant(nutrition="none"), "nutrition"),
        (_variant(id="not url safe"), "id"),
        (_variant(prep_minutes=0), "prep_minutes"),
        (_variant(cook_minutes=-5), "cook_minutes"),
        (_variant(difficulty="Expert"), "difficulty"),
        (_variant(servings=0), "servings"),
        (_variant(ingredients=[]), "ingredients"),
        (_variant(steps=["One.", "Two."]), "steps"),
        (_variant(colors=["#E9B44C"]), "colors"),
        (_variant(colors=["#E9B44C", "#3F6B4F", "#C9472D"]), "colors"),
        (_variant(featured="true"), "featured"),
    ],
)
def test_malformed_recipe_names_the_recipe_and_the_field(tmp_path, recipe, field):
    with pytest.raises(ValueError) as excinfo:
        load_recipes(_write(tmp_path, [recipe]))
    message = str(excinfo.value)
    assert field in message, message
    assert recipe.get("id", "0") in message or "position 0" in message, message


def test_duplicate_id_is_rejected_by_the_collection_builder():
    with pytest.raises(ValueError) as excinfo:
        build_collection([copy.deepcopy(BASE_RECIPE), copy.deepcopy(BASE_RECIPE)])
    assert "test-frittata" in str(excinfo.value)
    assert "id" in str(excinfo.value)


def test_validate_recipe_returns_a_valid_recipe():
    assert validate_recipe(copy.deepcopy(BASE_RECIPE), 0)["id"] == "test-frittata"


# --------------------------------------------------------------------------- #
# search helpers and total time
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  LENTIL  ", "lentil"), ("Plum", "plum"), ("", ""), ("   ", ""), (None, ""), (3, "")],
)
def test_normalise_query(raw, expected):
    assert normalise_query(raw) == expected


def test_searchable_text_is_folded_and_spans_five_fields():
    text = searchable_text(BASE_RECIPE)
    assert text == text.casefold()
    assert "test frittata" in text
    assert "loader tests" in text
    assert "breakfast" in text
    assert "vegetarian" in text
    assert "courgette" in text


@pytest.mark.parametrize(
    "query",
    ["Test Frittata", "  LOADER tests ", "breakfast", " VEGETARIAN", "Courgette"],
)
def test_recipe_matches_ignores_case_and_padding(query):
    assert recipe_matches(BASE_RECIPE, query) is True


def test_recipe_matches_rejects_an_absent_term():
    assert recipe_matches(BASE_RECIPE, "saffron") is False


@pytest.mark.parametrize("query", ["", "  ", None, 0, ["x"]])
def test_blank_or_non_string_query_matches_everything(collection, query):
    assert filter_recipes(collection.recipes, query) == list(collection.recipes)


def test_filter_recipes_preserves_collection_order(collection):
    filtered = filter_recipes(collection.recipes, " PLUM ")
    assert [r["id"] for r in filtered] == [
        r["id"] for r in collection.recipes if recipe_matches(r, "plum")
    ]
    assert filtered
    assert filter_recipes(collection.recipes, "no-such-ingredient") == []


def test_total_minutes_is_prep_plus_cook(collection):
    for recipe in collection.recipes:
        assert total_minutes(recipe) == recipe["prep_minutes"] + recipe["cook_minutes"]


def test_total_minutes_with_zero_cook_time(collection):
    no_cook = [r for r in collection.recipes if r["cook_minutes"] == 0]
    assert no_cook, "the fixture should include at least one no-cook recipe"
    for recipe in no_cook:
        assert total_minutes(recipe) == recipe["prep_minutes"]
    assert total_minutes(_variant(prep_minutes=12, cook_minutes=0)) == 12
