"""Implementation-owned tests for the TableStory pages, API and legacy cutover."""

import re
from pathlib import Path

from page_routes import EMPTY_STATE, TAGLINE, cookbook_control_label
from rails import RAIL_NAMES
from recipe_data import load_recipes
from recipe_search import total_minutes

UNKNOWN_ID = "no-such-recipe"

APP_DIR = Path(__file__).resolve().parents[1]

# The cinema surface this ticket removes atomically: no alias, shim or leftover
# file may survive the change (D_HARD_CUTOVER).
REMOVED_FILES = (
    "catalog.json",
    "templates/index.html",
    "templates/detail.html",
    "static/app.js",
    "static/app-logic.js",
    "static/tests/app-logic.test.js",
)


def _collection():
    return load_recipes()


def _card_blocks(html):
    """The rendered markup of each recipe card, keyed by recipe id."""
    blocks = re.findall(
        r'<article class="recipe-card" data-recipe-id="([^"]+)"(.*?)</article>',
        html,
        re.DOTALL,
    )
    return dict(blocks)


def test_browse_renders_one_card_per_recipe(client):
    collection = _collection()
    html = client.get("/").get_data(as_text=True)

    links = re.findall(r'href="(/recipe/[^"]+)"', html)
    assert len(links) == len(collection.recipes)
    assert sorted(links) == sorted(f"/recipe/{r['id']}" for r in collection.recipes)
    assert TAGLINE in html
    assert f"{len(collection.recipes)} recipes" in html

    cards = _card_blocks(html)
    assert sorted(cards) == sorted(recipe["id"] for recipe in collection.recipes)

    for recipe in collection.recipes:
        # Assert inside the card's own markup, so a value present elsewhere on
        # the page cannot stand in for a card that is missing it.
        card = cards[recipe["id"]]
        assert recipe["title"] in card
        assert f'class="recipe-card-difficulty">{recipe["difficulty"]}<' in card
        # Total time is asserted against prep + cook from the fixture rather than
        # against the helper the page itself uses (R10).
        expected_total = recipe["prep_minutes"] + recipe["cook_minutes"]
        assert expected_total == total_minutes(recipe)
        assert f'class="recipe-card-time">{expected_total} min total<' in card
        assert f'href="/recipe/{recipe["id"]}"' in card
        # At least one category or dietary label per card (R10).
        assert any(
            f'class="recipe-card-label">{label}<' in card
            for label in (recipe["category"], *recipe["dietary_tags"])
        ), recipe["id"]
        # A labelled My Cookbook control in its unsaved state (R12).
        expected_label = cookbook_control_label(recipe["title"], False)
        assert f'aria-label="{expected_label}"' in card
        assert 'aria-pressed="false"' in card


def test_cinema_era_files_are_deleted():
    for relative in REMOVED_FILES:
        assert not (APP_DIR / relative).exists(), relative

    # The node gate globs this directory, so it must never be left empty.
    assert list((APP_DIR / "static" / "tests").glob("*.test.js"))


def test_every_card_link_opens_a_recipe_page(client):
    html = client.get("/").get_data(as_text=True)
    for href in set(re.findall(r'href="(/recipe/[^"]+)"', html)):
        assert client.get(href).status_code == 200, href


def test_browse_navigation_is_browse_only(client):
    html = client.get("/").get_data(as_text=True)
    assert "#watchlist" not in html
    assert "#profile" not in html
    assert "avatar" not in html
    assert EMPTY_STATE in html
    assert re.search(r"<[^<>]*hidden[^<>]*>" + re.escape(EMPTY_STATE), html)


def test_recipe_page_and_unknown_ids(client):
    recipe = _collection().recipes[0]
    page = client.get(f"/recipe/{recipe['id']}")
    assert page.status_code == 200
    assert recipe["description"] in page.get_data(as_text=True)

    assert client.get(f"/recipe/{UNKNOWN_ID}").status_code == 404

    missing = client.get(f"/api/recipes/{UNKNOWN_ID}")
    assert missing.status_code == 404
    assert missing.get_json() == {"error": "Recipe not found"}


def test_api_recipes_filters_by_query(client):
    collection = _collection()
    assert len(client.get("/api/recipes").get_json()) == len(collection.recipes)
    assert client.get("/api/recipes?q=zzz-nothing").get_json() == []
    vegan = client.get("/api/recipes?q=  VEGAN ").get_json()
    assert vegan and all("Vegan" in r["dietary_tags"] for r in vegan)


def test_cookbook_round_trip(client):
    first, second = _collection().recipes[0], _collection().recipes[1]
    assert client.get("/api/cookbook").get_json() == []

    created = client.post("/api/cookbook", json={"id": first["id"]})
    assert created.status_code == 201
    assert created.get_json()["recipe_ids"] == [first["id"]]
    assert client.get("/api/cookbook").get_json() == [first]

    client.post("/api/cookbook", json={"id": second["id"]})
    removed = client.delete(f"/api/cookbook/{first['id']}")
    assert removed.status_code == 200
    assert removed.get_json()["recipe_ids"] == [second["id"]]

    again = client.delete(f"/api/cookbook/{first['id']}")
    assert again.status_code == 200

    unknown = client.post("/api/cookbook", json={"id": UNKNOWN_ID})
    assert unknown.status_code == 400
    assert "recipe" in unknown.get_json()["error"].lower()

    malformed = client.post(
        "/api/cookbook", data="{nope", content_type="application/json"
    )
    assert malformed.status_code == 400
    assert "recipe" in malformed.get_json()["error"].lower()


def test_api_rails_exposes_recipe_ids(client):
    rails = client.get("/api/rails").get_json()
    assert [rail["name"] for rail in rails] == list(RAIL_NAMES)
    known = {recipe["id"] for recipe in _collection().recipes}
    for rail in rails:
        assert set(rail) == {"name", "recipe_ids"}
        assert set(rail["recipe_ids"]) <= known


def test_no_supported_response_exposes_movie_ids(client):
    recipe_id = _collection().recipes[0]["id"]
    client.post("/api/cookbook", json={"id": recipe_id})
    paths = (
        "/api/recipes",
        f"/api/recipes/{recipe_id}",
        "/api/cookbook",
        "/api/rails",
        "/",
        f"/recipe/{recipe_id}",
    )
    for path in paths:
        body = client.get(path).get_data(as_text=True)
        assert "movie_ids" not in body, path


def test_legacy_cinema_routes_are_gone(client):
    for method, path in (
        ("GET", "/movie/afterlight"),
        ("GET", "/api/movies"),
        ("GET", "/api/movies/afterlight"),
        ("GET", "/api/watchlist"),
        ("POST", "/api/watchlist"),
        ("DELETE", "/api/watchlist/afterlight"),
    ):
        response = client.open(path, method=method)
        assert response.status_code == 404, f"{method} {path} answered {response.status_code}"
