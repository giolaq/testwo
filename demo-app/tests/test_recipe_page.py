"""The mobile recipe page: GET /recipe/<recipe_id> rendered from detail_context.

Every expectation is derived from the loaded collection through the public
loader, so the assertions follow demo-app/recipes.json instead of freezing
literals. Saved state is flipped through the public cookbook API because the
client-side toggle belongs to a later slice.
"""

from __future__ import annotations

import re

import pytest
from page_routes import BROWSE_PATH, cookbook_control_label
from recipe_data import load_recipes
from recipe_search import total_minutes

COLLECTION = load_recipes()
RECIPES = list(COLLECTION.recipes)
SAMPLE = RECIPES[0]


def _first(predicate) -> dict:
    for recipe in RECIPES:
        if predicate(recipe):
            return recipe
    pytest.fail("the recipe fixture no longer contains a recipe for this case")


NO_TAGS = _first(lambda recipe: not recipe["dietary_tags"])
ZERO_COOK = _first(lambda recipe: recipe["cook_minutes"] == 0)


def _detail(client, recipe: dict) -> str:
    response = client.get(f"/recipe/{recipe['id']}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _ordered_positions(html: str, items) -> None:
    """Assert every item appears, each one after the previous."""
    cursor = 0
    for item in items:
        found = html.find(item, cursor)
        assert found != -1, f"{item!r} missing or out of stored order"
        cursor = found + len(item)


def _button(html: str, recipe_id: str) -> str:
    controls = [
        match.group(0)
        for match in re.finditer(
            r"<button\b[^>]*>.*?</button\s*>", html, re.DOTALL | re.IGNORECASE
        )
        if recipe_id in match.group(0)
    ]
    assert len(controls) == 1, f"expected one My Cookbook control for {recipe_id!r}"
    return controls[0]


def _attr(markup: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', markup)
    return None if match is None else match.group(1)


def _visible_text(markup: str) -> str:
    return re.sub(r"<[^>]*>", " ", re.sub(r"<!--.*?-->", " ", markup, flags=re.DOTALL))


@pytest.mark.parametrize("recipe", RECIPES, ids=[r["id"] for r in RECIPES])
def test_detail_page_renders_the_nine_attributes(client, recipe):
    html = _detail(client, recipe)
    total = total_minutes(recipe)

    assert recipe["title"] in html
    assert recipe["description"] in html
    assert recipe["category"] in html
    for tag in recipe["dietary_tags"]:
        assert tag in html
    assert recipe["difficulty"] in html
    for label, value in (
        ("Prep time", recipe["prep_minutes"]),
        ("Cook time", recipe["cook_minutes"]),
        ("Total time", total),
    ):
        assert re.search(
            rf"{label}</dt>\s*<dd[^>]*>\s*{value} min", html
        ), f"{recipe['id']!r} must show {label} as {value} min"
    assert re.search(rf"Serves</dt>\s*<dd[^>]*>\s*{recipe['servings']}\b", html)


@pytest.mark.parametrize("recipe", RECIPES, ids=[r["id"] for r in RECIPES])
def test_detail_page_lists_ingredients_and_numbered_steps_in_stored_order(
    client, recipe
):
    html = _detail(client, recipe)
    _ordered_positions(html, recipe["ingredients"])

    method = re.search(r"<ol\b[^>]*>(.*?)</ol\s*>", html, re.DOTALL)
    assert method is not None, "method steps must be an ordered list"
    _ordered_positions(method.group(1), recipe["steps"])
    assert len(re.findall(r"<li\b", method.group(1))) == len(recipe["steps"])


def test_detail_control_names_the_recipe_and_states_the_add_action(client):
    control = _button(_detail(client, SAMPLE), SAMPLE["id"])
    assert _attr(control, "aria-label") == cookbook_control_label(
        SAMPLE["title"], False
    )
    assert _attr(control, "aria-pressed") == "false"
    assert "Save" in _visible_text(control)


def test_detail_control_states_the_remove_action_once_saved(client):
    assert client.post("/api/cookbook", json={"id": SAMPLE["id"]}).status_code == 201

    control = _button(_detail(client, SAMPLE), SAMPLE["id"])
    assert _attr(control, "aria-label") == cookbook_control_label(SAMPLE["title"], True)
    assert _attr(control, "aria-pressed") == "true"
    assert "Saved" in _visible_text(control)


def test_detail_control_matches_the_browse_card_control(client):
    """The same saved-state boolean drives both surfaces."""
    assert client.post("/api/cookbook", json={"id": SAMPLE["id"]}).status_code == 201

    detail = _button(_detail(client, SAMPLE), SAMPLE["id"])
    card = _button(client.get(BROWSE_PATH).get_data(as_text=True), SAMPLE["id"])
    assert _attr(detail, "aria-label") == _attr(card, "aria-label")
    assert _attr(detail, "aria-pressed") == _attr(card, "aria-pressed") == "true"


@pytest.mark.parametrize("recipe", RECIPES, ids=[r["id"] for r in RECIPES])
def test_detail_page_carries_both_recipe_colours_as_custom_properties(client, recipe):
    html = _detail(client, recipe)
    assert f"--artwork-a: {recipe['colors'][0]}" in html
    assert f"--artwork-b: {recipe['colors'][1]}" in html


def test_detail_back_action_targets_the_mobile_browse_page(client):
    html = _detail(client, SAMPLE)
    back = re.search(r'<a class="back" href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
    assert back is not None, "the recipe page must offer a back action"
    assert back.group(1) == BROWSE_PATH
    assert back.group(2).strip()
    assert client.get(BROWSE_PATH).status_code == 200


def test_a_recipe_with_no_dietary_tags_renders_no_empty_label_area(client):
    html = _detail(client, NO_TAGS)
    assert NO_TAGS["category"] in html
    assert "recipe-dietary" not in html, (
        f"{NO_TAGS['id']!r} has no dietary tags, so the dietary label list must "
        "not be rendered at all"
    )
    for tag in {t for r in RECIPES for t in r["dietary_tags"]}:
        assert not re.search(rf">\s*{re.escape(tag)}\s*<", html)


def test_a_recipe_with_zero_cook_minutes_shows_prep_as_the_total(client):
    assert total_minutes(ZERO_COOK) == ZERO_COOK["prep_minutes"]
    html = _detail(client, ZERO_COOK)
    assert re.search(r"Cook time</dt>\s*<dd[^>]*>\s*0 min", html)
    assert re.search(
        rf"Total time</dt>\s*<dd[^>]*>\s*{ZERO_COOK['prep_minutes']} min", html
    )


def test_an_unknown_recipe_id_returns_404(client):
    assert client.get("/recipe/not-a-stored-recipe").status_code == 404
    assert client.get(f"/recipe/{SAMPLE['id']}-suffix").status_code == 404
