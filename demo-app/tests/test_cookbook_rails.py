"""Tests for the in-memory My Cookbook store and the derived TV rails.

Exercises demo-app/cookbook.py and demo-app/rails.py through their public
functions only. Deterministic and offline: the single input is the local recipe
fixture loaded by the ticket #1 loader.
"""

import pytest

from cookbook import CookbookStore, UnknownRecipeError
from rails import (
    COOKBOOK_EMPTY_STATE,
    COOKBOOK_RAIL_NAME,
    QUICK_MINUTES,
    RAIL_NAMES,
    VEGETARIAN_TAG,
    build_rails,
    cookbook_rail,
    rail_members,
)
from recipe_data import load_recipes
from recipe_search import total_minutes

MIN_RAIL_RECIPES = 2


@pytest.fixture()
def collection():
    return load_recipes()


@pytest.fixture()
def store(collection):
    return CookbookStore(collection)


def ids(collection, count):
    return [recipe["id"] for recipe in collection.recipes[:count]]


def rails_by_name(collection, saved_ids=()):
    return {rail["name"]: rail for rail in build_rails(collection, list(saved_ids))}


# --------------------------------------------------------------------------- #
# CookbookStore
# --------------------------------------------------------------------------- #
def test_add_saves_in_insertion_order(collection, store):
    first, second = ids(collection, 2)
    assert store.list() == []
    assert store.add(second) == [second]
    assert store.add(first) == [second, first]
    assert store.list() == [second, first]


def test_add_rejects_an_unknown_id(store):
    with pytest.raises(UnknownRecipeError):
        store.add("not-a-recipe")
    assert store.list() == []


def test_re_add_is_a_successful_no_op(collection, store):
    first, second = ids(collection, 2)
    store.add(first)
    store.add(second)
    assert store.add(first) == [first, second]


def test_list_returns_a_copy(collection, store):
    (first,) = ids(collection, 1)
    store.add(first)
    returned = store.list()
    returned.append("injected")
    assert store.list() == [first]


def test_remove_is_idempotent(collection, store):
    first, second = ids(collection, 2)
    store.add(first)
    store.add(second)
    assert store.remove(first) == [second]
    assert store.remove(first) == [second]
    assert store.remove("never-existed") == [second]


def test_saved_recipes_resolves_full_objects_in_saved_order(collection, store):
    third, first = collection.recipes[2]["id"], collection.recipes[0]["id"]
    store.add(third)
    store.add(first)
    saved = store.saved_recipes()
    assert [recipe["id"] for recipe in saved] == [third, first]
    assert saved[0] is collection.by_id[third]
    assert store.saved_recipes() != []


def test_stores_are_independent(collection):
    (first,) = ids(collection, 1)
    one, other = CookbookStore(collection), CookbookStore(collection)
    one.add(first)
    assert one.list() == [first]
    assert other.list() == []


# --------------------------------------------------------------------------- #
# Rails
# --------------------------------------------------------------------------- #
def test_build_rails_returns_the_four_names_in_order(collection):
    rails = build_rails(collection, [])
    assert [rail["name"] for rail in rails] == list(RAIL_NAMES)


def test_non_cookbook_rails_hold_at_least_two_recipes(collection):
    rails = rails_by_name(collection)
    for name in RAIL_NAMES:
        if name == COOKBOOK_RAIL_NAME:
            continue
        assert len(rails[name]["recipe_ids"]) >= MIN_RAIL_RECIPES, name


def test_every_rail_id_resolves_to_a_collection_recipe(collection):
    saved = ids(collection, 1)
    for rail in build_rails(collection, saved):
        for recipe_id in rail["recipe_ids"]:
            assert recipe_id in collection.by_id


def test_membership_is_derived_from_the_recipe_data(collection):
    rails = rails_by_name(collection)

    def expected(predicate):
        return [r["id"] for r in collection.recipes if predicate(r)]

    assert rails["Popular this week"]["recipe_ids"] == expected(
        lambda r: r["featured"]
    )
    assert rails["Ready in 30 minutes"]["recipe_ids"] == expected(
        lambda r: total_minutes(r) <= QUICK_MINUTES
    )
    assert rails["Vegetarian favourites"]["recipe_ids"] == expected(
        lambda r: VEGETARIAN_TAG in r["dietary_tags"]
    )


def test_rail_members_uses_the_predicate_it_is_given(collection):
    assert rail_members(collection, lambda recipe: False) == []
    only = collection.recipes[1]["id"]
    selected = rail_members(collection, lambda recipe: recipe["id"] == only)
    assert [recipe["id"] for recipe in selected] == [only]


def test_rails_expose_recipe_ids_and_no_cinema_key(collection):
    for rail in build_rails(collection, ids(collection, 1)):
        assert "recipe_ids" in rail
        assert "movie_ids" not in rail
        assert all("movie" not in key and "film" not in key for key in rail)


def test_cookbook_rail_preserves_saved_order_and_skips_stale_ids(collection):
    saved = [collection.recipes[3]["id"], collection.recipes[0]["id"], "stale-id"]
    rail = cookbook_rail(collection, saved)
    assert rail["recipe_ids"] == saved[:2]
    assert rail["name"] == COOKBOOK_RAIL_NAME


def test_empty_cookbook_rail_carries_recipe_domain_empty_state(collection):
    rail = rails_by_name(collection)[COOKBOOK_RAIL_NAME]
    assert rail["recipe_ids"] == []
    assert rail["empty_state"] == COOKBOOK_EMPTY_STATE
    assert "My Cookbook" in COOKBOOK_EMPTY_STATE
    assert "recipe" in COOKBOOK_EMPTY_STATE.lower()


def test_build_rails_does_not_mutate_the_saved_id_list(collection):
    saved = ids(collection, 2)
    original = list(saved)
    build_rails(collection, saved)
    assert saved == original


def test_composed_rails_report_their_resolved_ids(collection, capsys):
    """Prints the composed rails so a reviewer can read them from the run output."""
    store = CookbookStore(collection)
    store.add(collection.recipes[0]["id"])
    with capsys.disabled():
        print()
        for rail in build_rails(collection, store.list()):
            print(f"{rail['name']}: {rail['recipe_ids']}")
    assert len(build_rails(collection, store.list())) == len(RAIL_NAMES)
