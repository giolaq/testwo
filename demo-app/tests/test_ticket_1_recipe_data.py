"""Acceptance tests for ticket #1: recipe fixture, validating loader, search helpers.

Scope is limited to the ticket's own files:
  demo-app/recipes.json, demo-app/recipe_data.py, demo-app/recipe_search.py

Imports of the ticket's modules are deliberately lazy and are guarded by a file
existence assertion first, so a missing module surfaces as a plain behaviour
assertion failure and never as an ImportError from this file.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

DEMO_APP = Path(__file__).parents[1]
FIXTURE_PATH = DEMO_APP / "recipes.json"

if str(DEMO_APP) not in sys.path:
    sys.path.insert(0, str(DEMO_APP))

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
DIFFICULTIES = {"Easy", "Medium", "Confident Cook"}
URL_SAFE_ID = re.compile(r"^[A-Za-z0-9._~-]+$")
CSS_COLOR = re.compile(
    r"^(#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})"
    r"|(?:rgb|rgba|hsl|hsla)\([^()]+\)"
    r"|[a-zA-Z]+)$"
)


# --------------------------------------------------------------------------- #
# lazy access helpers
# --------------------------------------------------------------------------- #
def _module(name: str):
    source = DEMO_APP / f"{name}.py"
    assert source.is_file(), f"ticket #1 requires demo-app/{name}.py"
    module = sys.modules.get(name)
    if module is not None and getattr(module, "__file__", None) == str(source):
        return module
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _attr(module_name: str, attr: str):
    module = _module(module_name)
    if not hasattr(module, attr):
        raise AssertionError(f"{module_name} must define {attr}")
    return getattr(module, attr)


def _fixture_raw():
    assert FIXTURE_PATH.is_file(), "ticket #1 requires demo-app/recipes.json"
    return json.loads(FIXTURE_PATH.read_text())


def _load_recipes(path=None):
    loader = _attr("recipe_data", "load_recipes")
    return loader(path) if path is not None else loader()


def _collection_parts(collection):
    """Return (recipes, by_id) for either a mapping-like or attribute-like collection."""
    if hasattr(collection, "recipes"):
        return collection.recipes, collection.by_id
    if isinstance(collection, dict) and "recipes" in collection:
        return collection["recipes"], collection["by_id"]
    if isinstance(collection, tuple) and len(collection) == 2:
        return collection
    raise AssertionError(
        "load_recipes must return a collection exposing the ordered recipes and an id index, "
        f"got {type(collection)!r}"
    )


def _recipes():
    return _collection_parts(_load_recipes())[0]


def _total_minutes(recipe):
    return _attr("recipe_search", "total_minutes")(recipe)


# --------------------------------------------------------------------------- #
# fixture file: presence, ordering, index
# --------------------------------------------------------------------------- #
def test_fixture_file_exists_and_is_a_json_array_of_at_least_twelve_recipes():
    raw = _fixture_raw()
    assert isinstance(raw, list), "recipes.json must be a JSON array"
    assert len(raw) >= 12, f"expected at least 12 recipes, found {len(raw)}"


def test_loader_returns_recipes_in_file_order_with_an_id_index():
    raw = _fixture_raw()
    recipes, by_id = _collection_parts(_load_recipes())

    assert [r["id"] for r in recipes] == [r["id"] for r in raw], (
        "load_recipes must preserve recipes.json file order"
    )
    assert isinstance(recipes, tuple), "the loaded collection must expose an immutable tuple"
    assert set(by_id) == {r["id"] for r in recipes}, "the id index must cover every recipe"
    for recipe in recipes:
        assert by_id[recipe["id"]]["title"] == recipe["title"]


def test_two_consecutive_loads_return_identical_ordering_and_content():
    first, _ = _collection_parts(_load_recipes())
    second, _ = _collection_parts(_load_recipes())
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert [dict(r) for r in first] == [dict(r) for r in second]


def test_loader_reads_local_files_only_with_no_network_or_environment_access():
    source = DEMO_APP / "recipe_data.py"
    assert source.is_file(), "ticket #1 requires demo-app/recipe_data.py"
    text = source.read_text()
    for forbidden in ("requests", "urllib", "http.client", "socket", "os.environ", "getenv"):
        assert forbidden not in text, (
            f"recipe_data.py must load local files only; found {forbidden!r}"
        )


# --------------------------------------------------------------------------- #
# per-recipe field rules
# --------------------------------------------------------------------------- #
def test_every_recipe_has_exactly_the_thirteen_recipe_fields():
    for position, recipe in enumerate(_recipes()):
        assert set(recipe) == set(RECIPE_FIELDS), (
            f"recipe at position {position} ({recipe.get('id')!r}) must carry exactly "
            f"{sorted(RECIPE_FIELDS)}"
        )


def test_every_recipe_satisfies_its_field_value_rules():
    seen_ids: set[str] = set()
    for recipe in _recipes():
        rid = recipe["id"]
        assert isinstance(rid, str) and URL_SAFE_ID.match(rid), f"{rid!r} is not a URL-safe id"
        assert rid not in seen_ids, f"duplicate recipe id {rid!r}"
        seen_ids.add(rid)

        assert isinstance(recipe["title"], str) and recipe["title"].strip(), f"{rid}: title"
        assert isinstance(recipe["description"], str) and recipe["description"].strip(), (
            f"{rid}: description"
        )
        assert isinstance(recipe["category"], str) and recipe["category"].strip(), (
            f"{rid}: category"
        )

        tags = recipe["dietary_tags"]
        assert isinstance(tags, list) and all(isinstance(t, str) and t.strip() for t in tags), (
            f"{rid}: dietary_tags"
        )

        prep = recipe["prep_minutes"]
        assert isinstance(prep, int) and not isinstance(prep, bool) and prep >= 1, (
            f"{rid}: prep_minutes must be an integer >= 1, got {prep!r}"
        )
        cook = recipe["cook_minutes"]
        assert isinstance(cook, int) and not isinstance(cook, bool) and cook >= 0, (
            f"{rid}: cook_minutes must be an integer >= 0, got {cook!r}"
        )
        assert recipe["difficulty"] in DIFFICULTIES, (
            f"{rid}: difficulty must be one of {sorted(DIFFICULTIES)}, got "
            f"{recipe['difficulty']!r}"
        )
        servings = recipe["servings"]
        assert isinstance(servings, int) and not isinstance(servings, bool) and servings >= 1, (
            f"{rid}: servings must be an integer >= 1, got {servings!r}"
        )

        ingredients = recipe["ingredients"]
        assert isinstance(ingredients, list) and ingredients, f"{rid}: ingredients must be non-empty"
        assert all(isinstance(i, str) and i.strip() for i in ingredients), f"{rid}: ingredients"

        steps = recipe["steps"]
        assert isinstance(steps, list) and len(steps) >= 3, (
            f"{rid}: steps must contain at least three instructions, got {len(steps)}"
        )
        assert all(isinstance(s, str) and s.strip() for s in steps), f"{rid}: steps"

        colors = recipe["colors"]
        assert isinstance(colors, list) and len(colors) == 2, (
            f"{rid}: colors must contain exactly two values, got {colors!r}"
        )
        for color in colors:
            assert isinstance(color, str) and CSS_COLOR.match(color.strip()), (
                f"{rid}: {color!r} is not a valid CSS color"
            )

        assert isinstance(recipe["featured"], bool), f"{rid}: featured must be a boolean"


# --------------------------------------------------------------------------- #
# content mix
# --------------------------------------------------------------------------- #
def _mix(recipes):
    return {
        "recipes": len(recipes),
        "vegetarian": sum(1 for r in recipes if "Vegetarian" in r["dietary_tags"]),
        "vegan": sum(1 for r in recipes if "Vegan" in r["dietary_tags"]),
        "total_time_30_or_less": sum(1 for r in recipes if _total_minutes(r) <= 30),
        "dessert": sum(1 for r in recipes if r["category"].casefold() == "dessert"),
        "featured": sum(1 for r in recipes if r["featured"]),
    }


def test_content_mix_thresholds_and_printed_summary():
    recipes = _recipes()
    mix = _mix(recipes)
    print(
        "recipe content mix: "
        f"recipes={mix['recipes']} "
        f"vegetarian={mix['vegetarian']} "
        f"vegan={mix['vegan']} "
        f"total_time<=30={mix['total_time_30_or_less']} "
        f"dessert={mix['dessert']} "
        f"featured={mix['featured']}"
    )
    assert mix["recipes"] >= 12, mix
    assert mix["vegetarian"] >= 3, mix
    assert mix["vegan"] >= 2, mix
    assert mix["total_time_30_or_less"] >= 3, mix
    assert mix["dessert"] >= 2, mix
    assert mix["featured"] >= 2, mix


def test_meal_categories_are_covered():
    categories = {r["category"].casefold() for r in _recipes()}
    for wanted in ("breakfast", "lunch", "dinner", "dessert"):
        assert wanted in categories, f"no recipe with category {wanted!r}; found {sorted(categories)}"


def test_recipe_content_is_unique_per_recipe():
    recipes = _recipes()
    for field in ("id", "title", "description"):
        values = [r[field] for r in recipes]
        assert len(set(values)) == len(values), f"duplicate {field} values in recipes.json"
    step_blocks = ["\n".join(r["steps"]) for r in recipes]
    assert len(set(step_blocks)) == len(step_blocks), "two recipes share identical steps"


# --------------------------------------------------------------------------- #
# malformed-fixture failure messages via the injected path
# --------------------------------------------------------------------------- #
VALID_RECIPE = {
    "id": "herb-omelette",
    "title": "Herb Omelette",
    "description": "A fast three-egg omelette folded around soft herbs.",
    "category": "Breakfast",
    "dietary_tags": ["Vegetarian"],
    "prep_minutes": 5,
    "cook_minutes": 6,
    "difficulty": "Easy",
    "servings": 1,
    "ingredients": ["3 eggs", "A handful of parsley", "1 tsp butter"],
    "steps": ["Beat the eggs.", "Melt the butter.", "Cook and fold with the herbs."],
    "colors": ["#E9B44C", "#3F6B4F"],
    "featured": True,
}
SECOND_RECIPE = {
    **copy.deepcopy(VALID_RECIPE),
    "id": "lentil-stew",
    "title": "Lentil Stew",
    "description": "A hearty pot of lentils simmered with root vegetables.",
    "category": "Dinner",
    "dietary_tags": ["Vegan"],
    "prep_minutes": 10,
    "cook_minutes": 35,
    "difficulty": "Medium",
    "servings": 4,
    "ingredients": ["200g lentils", "2 carrots", "1 onion"],
    "steps": ["Chop the vegetables.", "Simmer with the lentils.", "Season and serve."],
    "featured": False,
}


def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "recipes.json"
    path.write_text(json.dumps(payload))
    return path


def test_injected_valid_fixture_loads_so_the_failure_cases_are_meaningful(tmp_path):
    path = _write(tmp_path, [copy.deepcopy(VALID_RECIPE), copy.deepcopy(SECOND_RECIPE)])
    recipes, by_id = _collection_parts(_load_recipes(path))
    assert [r["id"] for r in recipes] == ["herb-omelette", "lentil-stew"]
    assert set(by_id) == {"herb-omelette", "lentil-stew"}


def _mutate(**changes):
    recipe = copy.deepcopy(VALID_RECIPE)
    for key, value in changes.items():
        if value is _REMOVE:
            recipe.pop(key)
        else:
            recipe[key] = value
    return recipe


class _Remove:
    pass


_REMOVE = _Remove()


INVALID_CASES = [
    ("missing key", _mutate(servings=_REMOVE), "servings"),
    ("extra key", _mutate(calories=420), "calories"),
    ("non-url-safe id", _mutate(id="herb omelette/1"), "id"),
    ("prep_minutes below one", _mutate(prep_minutes=0), "prep_minutes"),
    ("negative cook_minutes", _mutate(cook_minutes=-1), "cook_minutes"),
    ("difficulty outside vocabulary", _mutate(difficulty="Hard"), "difficulty"),
    ("servings below one", _mutate(servings=0), "servings"),
    ("empty ingredients", _mutate(ingredients=[]), "ingredients"),
    ("fewer than three steps", _mutate(steps=["Beat the eggs.", "Fold."]), "steps"),
    ("one color", _mutate(colors=["#E9B44C"]), "colors"),
    ("three colors", _mutate(colors=["#E9B44C", "#3F6B4F", "#C9472D"]), "colors"),
    ("non-boolean featured", _mutate(featured="yes"), "featured"),
]


@pytest.mark.parametrize(
    ("case", "recipe", "field"),
    INVALID_CASES,
    ids=[c[0].replace(" ", "-") for c in INVALID_CASES],
)
def test_malformed_recipe_is_rejected_naming_the_recipe_and_field(tmp_path, case, recipe, field):
    path = _write(tmp_path, [recipe])
    with pytest.raises(ValueError) as excinfo:
        _load_recipes(path)
    message = str(excinfo.value)
    assert field in message, f"{case}: ValueError must name the {field!r} field, got: {message}"
    identifier = recipe.get("id", "0")
    assert identifier in message or "0" in message, (
        f"{case}: ValueError must name the offending recipe id or file position, got: {message}"
    )


def test_duplicate_recipe_id_is_rejected_naming_the_id(tmp_path):
    path = _write(tmp_path, [copy.deepcopy(VALID_RECIPE), copy.deepcopy(VALID_RECIPE)])
    with pytest.raises(ValueError) as excinfo:
        _load_recipes(path)
    message = str(excinfo.value)
    assert "herb-omelette" in message, message
    assert "id" in message, message


def test_validate_recipe_and_build_collection_are_available_as_named_helpers(tmp_path):
    validate = _attr("recipe_data", "validate_recipe")
    build = _attr("recipe_data", "build_collection")

    validated = validate(copy.deepcopy(VALID_RECIPE), 0)
    assert validated["id"] == "herb-omelette"
    with pytest.raises(ValueError):
        validate(_mutate(difficulty="Hard"), 0)

    recipes, by_id = _collection_parts(
        build([copy.deepcopy(VALID_RECIPE), copy.deepcopy(SECOND_RECIPE)])
    )
    assert [r["id"] for r in recipes] == ["herb-omelette", "lentil-stew"]
    assert isinstance(recipes, tuple)
    assert set(by_id) == {"herb-omelette", "lentil-stew"}
    with pytest.raises(ValueError):
        build([copy.deepcopy(VALID_RECIPE), copy.deepcopy(VALID_RECIPE)])


# --------------------------------------------------------------------------- #
# search helpers
# --------------------------------------------------------------------------- #
def test_normalise_query_strips_and_casefolds_and_degrades_non_strings():
    normalise = _attr("recipe_search", "normalise_query")
    assert normalise("  LeNTil  ") == "lentil"
    assert normalise("") == ""
    assert normalise("   ") == ""
    assert normalise(None) == ""
    assert normalise(42) == ""
    assert normalise(["lentil"]) == ""


def test_searchable_text_covers_the_five_searchable_fields_case_folded():
    searchable = _attr("recipe_search", "searchable_text")
    text = searchable(copy.deepcopy(VALID_RECIPE))
    assert text == text.casefold(), "searchable text must be case-folded"
    for expected in (
        VALID_RECIPE["title"].casefold(),
        VALID_RECIPE["description"].casefold(),
        VALID_RECIPE["category"].casefold(),
        VALID_RECIPE["dietary_tags"][0].casefold(),
        VALID_RECIPE["ingredients"][1].casefold(),
    ):
        assert expected in text, f"{expected!r} missing from searchable text: {text!r}"


@pytest.mark.parametrize(
    "query",
    [
        "Herb Omelette",
        "  three-egg  ",
        "BREAKFAST",
        "vegetarian",
        "PARSLEY",
    ],
    ids=["title", "description-padded", "category", "dietary-tag", "ingredient"],
)
def test_recipe_matches_case_insensitively_across_every_searchable_field(query):
    matches = _attr("recipe_search", "recipe_matches")
    assert matches(copy.deepcopy(VALID_RECIPE), query) is True


def test_recipe_matches_rejects_a_term_absent_from_every_searchable_field():
    matches = _attr("recipe_search", "recipe_matches")
    assert matches(copy.deepcopy(VALID_RECIPE), "chocolate") is False


@pytest.mark.parametrize("query", ["", "   ", None, 7], ids=["empty", "blank", "none", "int"])
def test_empty_or_non_string_query_matches_every_recipe(query):
    matches = _attr("recipe_search", "recipe_matches")
    filter_recipes = _attr("recipe_search", "filter_recipes")
    recipes = _recipes()
    assert all(matches(r, query) is True for r in recipes)
    assert [r["id"] for r in filter_recipes(recipes, query)] == [r["id"] for r in recipes]


def test_filter_recipes_preserves_collection_order_and_returns_only_matches():
    filter_recipes = _attr("recipe_search", "filter_recipes")
    matches = _attr("recipe_search", "recipe_matches")
    recipes = _recipes()

    query = "  E  "
    filtered = filter_recipes(recipes, query)
    expected = [r["id"] for r in recipes if matches(r, query)]
    assert [r["id"] for r in filtered] == expected
    assert len(expected) >= 2, "sanity: the shared letter query should match several recipes"

    assert filter_recipes(recipes, "zzzz-no-such-ingredient") == []


def test_total_minutes_is_prep_plus_cook_including_a_zero_cook_recipe():
    for recipe in _recipes():
        assert _total_minutes(recipe) == recipe["prep_minutes"] + recipe["cook_minutes"]

    no_cook = _mutate(cook_minutes=0, prep_minutes=15)
    assert _total_minutes(no_cook) == 15


def test_search_module_stays_free_of_flask():
    source = DEMO_APP / "recipe_search.py"
    assert source.is_file(), "ticket #1 requires demo-app/recipe_search.py"
    imports_flask = re.search(
        r"^\s*(?:import\s+flask|from\s+flask\b)", source.read_text(), re.IGNORECASE | re.MULTILINE
    )
    assert imports_flask is None, (
        "recipe_search.py must contain only pure helpers with no web framework import"
    )
