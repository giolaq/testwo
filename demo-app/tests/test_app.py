"""Implementation-owned tests for the TableStory pages, API and legacy cutover."""

import re

from page_routes import EMPTY_STATE, TAGLINE
from rails import RAIL_NAMES
from recipe_data import load_recipes
from recipe_search import total_minutes

UNKNOWN_ID = "no-such-recipe"


def _collection():
    return load_recipes()


def test_browse_renders_one_card_per_recipe(client):
    collection = _collection()
    html = client.get("/").get_data(as_text=True)

    links = re.findall(r'href="(/recipe/[^"]+)"', html)
    assert len(links) == len(collection.recipes)
    assert sorted(links) == sorted(f"/recipe/{r['id']}" for r in collection.recipes)
    assert TAGLINE in html
    assert f"{len(collection.recipes)} recipes" in html

    for recipe in collection.recipes:
        assert recipe["title"] in html
        assert recipe["difficulty"] in html
        assert str(total_minutes(recipe)) in html


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
