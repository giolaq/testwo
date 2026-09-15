"""Acceptance tests for ticket #2: in-memory My Cookbook store and derived TV rails.

Scope is limited to the ticket's own files:
  demo-app/cookbook.py  (TYPE_COOKBOOK per C_COOKBOOK_STORE)
  demo-app/rails.py     (C_RAILS rail composition)

The ticket registers no routes and changes no existing file, so every assertion
here goes through those two modules plus the already-merged ticket #1 loader and
search helpers. Imports of the ticket's modules are deliberately lazy behind a
file-existence assertion, so a missing module surfaces as a behaviour assertion
failure rather than as a collection-time ImportError.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

DEMO_APP = Path(__file__).parents[1]

if str(DEMO_APP) not in sys.path:
    sys.path.insert(0, str(DEMO_APP))

RAIL_NAMES = (
    "Popular this week",
    "Ready in 30 minutes",
    "Vegetarian favourites",
    "My Cookbook",
)
COOKBOOK_RAIL_NAME = "My Cookbook"
QUICK_MINUTES = 30
VEGETARIAN_TAG = "Vegetarian"
MIN_RAIL_RECIPES = 2

# Cinema-domain vocabulary that must not appear in a rail structure's keys or in
# the cookbook rail's empty-state text (R5 / R29 recipe_ids-not-movie_ids).
CINEMA_TERMS = re.compile(
    r"\b(pocket cinema|cinema|movies?|films?|watchlist|posters?|runtime|genres?)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# lazy access helpers
# --------------------------------------------------------------------------- #
def _module(name: str):
    source = DEMO_APP / f"{name}.py"
    assert source.is_file(), f"ticket #2 requires demo-app/{name}.py"
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
        raise AssertionError(f"demo-app/{module_name}.py must define {attr}")
    return getattr(module, attr)


def _collection():
    """The validated ticket #1 recipe collection."""
    return _attr("recipe_data", "load_recipes")()


def _recipes(collection=None):
    collection = _collection() if collection is None else collection
    if hasattr(collection, "recipes"):
        return list(collection.recipes)
    if isinstance(collection, dict) and "recipes" in collection:
        return list(collection["recipes"])
    raise AssertionError(
        "load_recipes must return a collection exposing the ordered recipes, "
        f"got {type(collection)!r}"
    )


def _total_minutes(recipe):
    return _attr("recipe_search", "total_minutes")(recipe)


def _store(collection=None):
    collection = _collection() if collection is None else collection
    return _attr("cookbook", "CookbookStore")(collection)


def _unknown_recipe_error():
    error = _attr("cookbook", "UnknownRecipeError")
    assert isinstance(error, type) and issubclass(error, Exception), (
        "cookbook.UnknownRecipeError must be an exception class defined by the module"
    )
    return error


def _build_rails(collection, saved_ids):
    return _attr("rails", "build_rails")(collection, saved_ids)


def _rail_list(railset):
    """Accept either a bare ordered sequence of rails or a {'rails': [...]} wrapper."""
    if isinstance(railset, (list, tuple)):
        return list(railset)
    if isinstance(railset, dict) and "rails" in railset:
        return list(railset["rails"])
    raise AssertionError(
        "build_rails must return an ordered set of four rails, "
        f"got {type(railset)!r}"
    )


def _rail_field(rail, key):
    if isinstance(rail, dict):
        assert key in rail, f"rail {rail!r} must expose {key!r}"
        return rail[key]
    assert hasattr(rail, key), f"rail {rail!r} must expose {key!r}"
    return getattr(rail, key)


def _rail_keys(rail):
    if isinstance(rail, dict):
        return list(rail.keys())
    return [name for name in dir(rail) if not name.startswith("_")]


def _rails_by_name(saved_ids=()):
    collection = _collection()
    rails = _rail_list(_build_rails(collection, list(saved_ids)))
    return {_rail_field(rail, "name"): rail for rail in rails}


def _expected_ids(predicate):
    return [recipe["id"] for recipe in _recipes() if predicate(recipe)]


def _first_ids(count):
    ids = [recipe["id"] for recipe in _recipes()]
    assert len(ids) >= count, "the recipe fixture is too small for this test"
    return ids[:count]


# --------------------------------------------------------------------------- #
# CookbookStore: add validation and re-add no-op
# --------------------------------------------------------------------------- #
def test_store_starts_empty_and_add_returns_the_updated_id_list():
    store = _store()
    assert store.list() == []

    first, second = _first_ids(2)
    assert store.add(first) == [first]
    assert store.add(second) == [first, second]
    assert store.list() == [first, second]


def test_add_rejects_an_id_absent_from_the_collection_with_unknown_recipe_error():
    store = _store()
    error = _unknown_recipe_error()

    with pytest.raises(error):
        store.add("no-such-recipe-id")

    assert store.list() == [], "a rejected save must not enter the cookbook"


def test_re_adding_an_already_saved_id_is_a_successful_no_op():
    store = _store()
    first, second = _first_ids(2)
    store.add(first)
    store.add(second)

    assert store.add(first) == [first, second], (
        "re-adding a saved recipe must succeed and must not duplicate or reorder it"
    )
    assert store.list() == [first, second]


def test_list_returns_insertion_order_and_a_caller_cannot_mutate_the_store():
    store = _store()
    ordered = _first_ids(3)
    # Save in reverse fixture order so insertion order is distinguishable from
    # both fixture order and sorted order.
    for recipe_id in reversed(ordered):
        store.add(recipe_id)

    expected = list(reversed(ordered))
    assert store.list() == expected

    leaked = store.list()
    leaked.append("injected-id")
    leaked.reverse()
    assert store.list() == expected, (
        "list() must return a copy so callers cannot mutate the store through it"
    )


# --------------------------------------------------------------------------- #
# CookbookStore: idempotent removal and saved-recipe resolution
# --------------------------------------------------------------------------- #
def test_remove_is_idempotent_for_an_absent_id_and_returns_the_unchanged_list():
    store = _store()
    first, second = _first_ids(2)
    store.add(first)
    store.add(second)

    assert store.remove(first) == [second]
    assert store.remove(first) == [second], "removing an absent id must still succeed"
    assert store.list() == [second]


def test_remove_succeeds_for_an_id_that_never_existed_in_the_collection():
    store = _store()
    (first,) = _first_ids(1)
    store.add(first)

    assert store.remove("never-existed-id") == [first]
    assert store.list() == [first]


def test_saved_recipes_returns_complete_recipe_objects_in_saved_order():
    store = _store()
    recipes = _recipes()
    by_id = {recipe["id"]: recipe for recipe in recipes}
    ordered = [recipes[2]["id"], recipes[0]["id"]]
    for recipe_id in ordered:
        store.add(recipe_id)

    saved = store.saved_recipes()
    assert [recipe["id"] for recipe in saved] == ordered, (
        "saved_recipes() must resolve ids in saved order"
    )
    for recipe in saved:
        assert recipe == by_id[recipe["id"]], (
            "saved_recipes() must return the complete recipe object, not a summary"
        )


def test_saved_recipes_is_empty_when_nothing_is_saved():
    assert _store().saved_recipes() == []


# --------------------------------------------------------------------------- #
# Rail composition: names, order, derivation, resolvability
# --------------------------------------------------------------------------- #
def test_build_rails_returns_exactly_four_rails_in_the_fixed_order():
    rails = _rail_list(_build_rails(_collection(), []))
    assert [_rail_field(rail, "name") for rail in rails] == list(RAIL_NAMES)


def test_every_non_cookbook_rail_holds_at_least_two_recipes_from_the_fixture():
    rails = _rails_by_name()
    for name in RAIL_NAMES:
        if name == COOKBOOK_RAIL_NAME:
            continue
        ids = _rail_field(rails[name], "recipe_ids")
        assert len(ids) >= MIN_RAIL_RECIPES, (
            f"rail {name!r} resolved {len(ids)} recipes; every non-cookbook rail "
            f"must hold at least {MIN_RAIL_RECIPES}"
        )


def test_every_rail_id_resolves_to_a_recipe_in_the_collection():
    known = {recipe["id"] for recipe in _recipes()}
    saved = _first_ids(1)
    rails = _rail_list(_build_rails(_collection(), saved))
    for rail in rails:
        for recipe_id in _rail_field(rail, "recipe_ids"):
            assert recipe_id in known, (
                f"rail {_rail_field(rail, 'name')!r} exposes unresolvable id {recipe_id!r}"
            )


def test_rail_membership_is_derived_from_featured_total_time_and_the_vegetarian_tag():
    rails = _rails_by_name()

    assert _rail_field(rails["Popular this week"], "recipe_ids") == _expected_ids(
        lambda recipe: bool(recipe["featured"])
    ), "'Popular this week' must be derived from the featured flag in fixture order"

    assert _rail_field(rails["Ready in 30 minutes"], "recipe_ids") == _expected_ids(
        lambda recipe: _total_minutes(recipe) <= QUICK_MINUTES
    ), "'Ready in 30 minutes' must be derived from prep + cook minutes <= 30"

    assert _rail_field(rails["Vegetarian favourites"], "recipe_ids") == _expected_ids(
        lambda recipe: VEGETARIAN_TAG in recipe["dietary_tags"]
    ), "'Vegetarian favourites' must be derived from the Vegetarian dietary tag"


def test_rail_members_is_predicate_driven_rather_than_hand_listed():
    rail_members = _attr("rails", "rail_members")
    collection = _collection()

    assert rail_members(collection, lambda recipe: False) == []

    only = _recipes(collection)[1]["id"]
    selected = rail_members(collection, lambda recipe: recipe["id"] == only)
    assert [recipe["id"] for recipe in selected] == [only], (
        "rail_members must select members using the predicate it is given"
    )


def test_the_quick_rail_boundary_includes_exactly_thirty_minutes_and_excludes_thirty_one():
    quick_ids = set(_rail_field(_rails_by_name()["Ready in 30 minutes"], "recipe_ids"))
    for recipe in _recipes():
        total = _total_minutes(recipe)
        if total <= QUICK_MINUTES:
            assert recipe["id"] in quick_ids, (
                f"{recipe['id']!r} totals {total} minutes and belongs in the quick rail"
            )
        else:
            assert recipe["id"] not in quick_ids, (
                f"{recipe['id']!r} totals {total} minutes and must not be in the quick rail"
            )


# --------------------------------------------------------------------------- #
# Rail structures: recipe-domain keys only
# --------------------------------------------------------------------------- #
def test_rails_expose_ids_under_recipe_ids_and_carry_no_cinema_domain_key():
    rails = _rail_list(_build_rails(_collection(), _first_ids(1)))
    for rail in rails:
        keys = _rail_keys(rail)
        assert "recipe_ids" in keys, (
            f"rail {_rail_field(rail, 'name')!r} must expose its ids under 'recipe_ids'"
        )
        assert "movie_ids" not in keys
        for key in keys:
            assert not CINEMA_TERMS.search(str(key)), (
                f"rail key {key!r} uses cinema-domain vocabulary"
            )
        ids = _rail_field(rail, "recipe_ids")
        assert isinstance(ids, list) and all(isinstance(value, str) for value in ids)


# --------------------------------------------------------------------------- #
# My Cookbook rail: saved order, refresh, empty state
# --------------------------------------------------------------------------- #
def test_the_cookbook_rail_preserves_saved_order():
    recipes = _recipes()
    saved = [recipes[3]["id"], recipes[1]["id"], recipes[0]["id"]]
    rail = _rails_by_name(saved)[COOKBOOK_RAIL_NAME]
    assert _rail_field(rail, "recipe_ids") == saved


def test_the_cookbook_rail_reflects_the_store_after_recomposition():
    collection = _collection()
    store = _store(collection)
    first, second = _first_ids(2)
    store.add(first)
    store.add(second)

    rails = {
        _rail_field(rail, "name"): rail
        for rail in _rail_list(_build_rails(collection, store.list()))
    }
    assert _rail_field(rails[COOKBOOK_RAIL_NAME], "recipe_ids") == [first, second]

    store.remove(first)
    rails = {
        _rail_field(rail, "name"): rail
        for rail in _rail_list(_build_rails(collection, store.list()))
    }
    assert _rail_field(rails[COOKBOOK_RAIL_NAME], "recipe_ids") == [second]


def test_the_cookbook_rail_skips_saved_ids_no_longer_in_the_collection():
    (known,) = _first_ids(1)
    rail = _rails_by_name([known, "stale-id-not-in-collection"])[COOKBOOK_RAIL_NAME]
    assert _rail_field(rail, "recipe_ids") == [known]


def test_the_empty_cookbook_rail_carries_recipe_domain_empty_state_text():
    rail = _rails_by_name([])[COOKBOOK_RAIL_NAME]
    assert _rail_field(rail, "recipe_ids") == []

    texts = [
        str(_rail_field(rail, key))
        for key in _rail_keys(rail)
        if "empty" in str(key).lower()
    ]
    non_empty = [text for text in texts if text.strip()]
    assert non_empty, (
        "the My Cookbook rail must carry empty-state text for the saved-nothing case"
    )
    for text in non_empty:
        assert not CINEMA_TERMS.search(text), (
            f"empty-state text {text!r} uses cinema-domain vocabulary"
        )
        assert re.search(r"recipe|cookbook|dish", text, re.IGNORECASE), (
            f"empty-state text {text!r} must use recipe-domain wording"
        )


# --------------------------------------------------------------------------- #
# Purity and dependency constraints (R27, R42)
# --------------------------------------------------------------------------- #
def test_build_rails_is_a_pure_function_of_its_arguments():
    collection = _collection()
    saved = _first_ids(2)
    first = _rail_list(_build_rails(collection, list(saved)))
    second = _rail_list(_build_rails(collection, list(saved)))

    def shape(rails):
        return [
            (_rail_field(rail, "name"), list(_rail_field(rail, "recipe_ids")))
            for rail in rails
        ]

    assert shape(first) == shape(second), "repeated composition must be identical"

    mutable = list(saved)
    _build_rails(collection, mutable)
    assert mutable == list(saved), "build_rails must not mutate the saved id list"


def test_two_stores_are_independent_so_saved_state_is_process_local_only():
    collection = _collection()
    (first,) = _first_ids(1)
    store_a = _store(collection)
    store_b = _store(collection)
    store_a.add(first)

    assert store_a.list() == [first]
    assert store_b.list() == [], (
        "each store owns its own in-memory saved set; no shared or persisted state"
    )


def test_the_ticket_modules_add_no_storage_or_flask_dependency():
    for name in ("cookbook", "rails"):
        source = DEMO_APP / f"{name}.py"
        assert source.is_file(), f"ticket #2 requires demo-app/{name}.py"
        text = source.read_text(encoding="utf-8")
        for forbidden in ("flask", "sqlite3", "sqlalchemy", "redis", "shelve", "pickle"):
            assert not re.search(
                rf"^\s*(?:import|from)\s+{forbidden}\b", text, re.IGNORECASE | re.MULTILINE
            ), f"demo-app/{name}.py must not depend on {forbidden}"
        assert "route(" not in text, f"demo-app/{name}.py must register no routes"
