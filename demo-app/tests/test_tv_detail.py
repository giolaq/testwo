"""The TV recipe detail page: GET /recipe/<recipe_id>?mode=tv.

Asserted through the public HTTP seam only, with every expectation derived from
the loaded collection so the tests follow demo-app/recipes.json rather than
frozen literals. The mobile detail page is asserted unchanged in
test_recipe_page.py; here the concern is TV template selection, the nine
attributes, the ordered content, the two stacked actions and mode retention.
"""

from __future__ import annotations

import re

import pytest
from page_routes import BROWSE_PATH, TV_DETAIL_TEMPLATE, cookbook_control_label
from recipe_data import load_recipes
from recipe_search import total_minutes
from view_mode import MODE_TV, QUERY_KEY

COLLECTION = load_recipes()
RECIPES = list(COLLECTION.recipes)
SAMPLE = RECIPES[0]

TV_QUERY = f"?{QUERY_KEY}={MODE_TV}"
TV_DETAIL_SCRIPT = "tv-detail.js"


def _first(predicate) -> dict:
    for recipe in RECIPES:
        if predicate(recipe):
            return recipe
    pytest.fail("the recipe fixture no longer contains a recipe for this case")


NO_TAGS = _first(lambda recipe: not recipe["dietary_tags"])
LONGEST_STEPS = max(RECIPES, key=lambda recipe: sum(len(s) for s in recipe["steps"]))


def _tv_detail(client, recipe: dict) -> str:
    response = client.get(f"/recipe/{recipe['id']}{TV_QUERY}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _ordered_positions(html: str, items) -> None:
    """Assert every item appears, each one after the previous."""
    cursor = 0
    for item in items:
        found = html.find(item, cursor)
        assert found != -1, f"{item!r} missing or out of stored order"
        cursor = found + len(item)


def _visible_text(markup: str) -> str:
    return re.sub(r"<[^>]*>", " ", re.sub(r"<!--.*?-->", " ", markup, flags=re.DOTALL))


def _attr(markup: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', markup)
    return None if match is None else match.group(1)


def _action_list(html: str) -> list[str]:
    """The stacked action list: the innermost list holding both TV actions."""
    lists = [
        match.group(1)
        for match in re.finditer(
            r"<(?:ol|ul)\b[^>]*\bdata-tv-actions\b[^>]*>(.*?)</(?:ol|ul)\s*>",
            html,
            re.DOTALL | re.IGNORECASE,
        )
    ]
    assert len(lists) == 1, "the TV detail page must render one ordered action list"
    items = re.findall(r"<li\b[^>]*>(.*?)</li\s*>", lists[0], re.DOTALL | re.IGNORECASE)
    assert len(items) == 2, "exactly two actions: back, then My Cookbook"
    return items


def _control(html: str, recipe_id: str) -> str:
    controls = [
        match.group(0)
        for match in re.finditer(
            r"<button\b[^>]*>.*?</button\s*>", html, re.DOTALL | re.IGNORECASE
        )
        if recipe_id in match.group(0)
    ]
    assert len(controls) == 1, f"expected one My Cookbook control for {recipe_id!r}"
    return controls[0]


def test_a_tv_resolved_detail_request_renders_the_tv_detail_template(client):
    html = _tv_detail(client, SAMPLE)
    assert TV_DETAIL_TEMPLATE == "tv_recipe.html"
    assert TV_DETAIL_SCRIPT in html, "the TV detail page loads its own binding"
    assert re.search(
        rf'<script[^>]*type="module"[^>]*{re.escape(TV_DETAIL_SCRIPT)}', html
    ), "the TV binding must load as a module"
    assert "1920" in (_attr(html, "content") or ""), "the layout targets 1920x1080"


def test_the_mobile_detail_page_does_not_load_the_tv_binding(client):
    html = client.get(f"/recipe/{SAMPLE['id']}").get_data(as_text=True)
    assert TV_DETAIL_SCRIPT not in html
    assert "data-tv-actions" not in html


@pytest.mark.parametrize("recipe", RECIPES, ids=[r["id"] for r in RECIPES])
def test_the_tv_detail_page_shows_all_nine_attributes(client, recipe):
    html = _tv_detail(client, recipe)
    text = _visible_text(html)

    assert recipe["title"] in html
    assert recipe["description"] in html
    assert recipe["category"] in text
    for tag in recipe["dietary_tags"]:
        assert re.search(rf">\s*{re.escape(tag)}\s*<", html), f"{tag} must be shown"
    assert recipe["difficulty"] in text
    for label, value in (
        ("Prep time", recipe["prep_minutes"]),
        ("Cook time", recipe["cook_minutes"]),
        ("Total time", total_minutes(recipe)),
    ):
        assert re.search(rf"{label}\s+{value} min", text), (
            f"{recipe['id']!r} must show {label} as {value} min"
        )
    assert re.search(rf"Serves\s+{recipe['servings']}\b", text)


def test_a_tv_recipe_with_no_dietary_tags_renders_no_tag_labels(client):
    html = _tv_detail(client, NO_TAGS)
    assert NO_TAGS["category"] in _visible_text(html)
    for tag in {t for r in RECIPES for t in r["dietary_tags"]}:
        assert not re.search(rf">\s*{re.escape(tag)}\s*<", html)


@pytest.mark.parametrize("recipe", RECIPES, ids=[r["id"] for r in RECIPES])
def test_the_tv_detail_page_lists_ingredients_and_numbered_steps_in_order(
    client, recipe
):
    html = _tv_detail(client, recipe)
    _ordered_positions(html, recipe["ingredients"])

    steps = [
        match.group(1)
        for match in re.finditer(r"<ol\b[^>]*>(.*?)</ol\s*>", html, re.DOTALL)
        if all(step in match.group(1) for step in recipe["steps"])
    ]
    assert steps, "the method steps must be a numbered (ordered) list"
    _ordered_positions(steps[-1], recipe["steps"])
    assert len(re.findall(r"<li\b", steps[-1])) == len(recipe["steps"])


def test_the_two_actions_are_stacked_in_order_and_reachable_without_a_pointer(client):
    html = _tv_detail(client, SAMPLE)
    back, cookbook = _action_list(html)

    assert re.search(r"<a\b[^>]*\bhref=", back), "the back action must be a link"
    assert _visible_text(back).strip(), "the back action needs visible text"

    assert SAMPLE["id"] in cookbook, "the second action is the My Cookbook control"
    assert re.search(r"<button\b", cookbook)
    assert _visible_text(cookbook).strip()


def test_the_long_step_recipe_still_renders_both_actions_before_its_content(client):
    """The action list sits above the long content, so scrolling cannot hide it."""
    html = _tv_detail(client, LONGEST_STEPS)
    _action_list(html)
    actions_at = html.find("data-tv-actions")
    assert actions_at != -1
    assert actions_at < html.find(LONGEST_STEPS["steps"][0])


def test_every_browse_target_on_the_tv_detail_page_retains_tv_mode(client):
    html = _tv_detail(client, SAMPLE)
    hrefs = re.findall(r'href="([^"]*)"', html)
    browse_hrefs = [
        href for href in hrefs if href.split("?")[0] == BROWSE_PATH
    ]
    assert browse_hrefs, "the page must offer a way back to browse"
    for href in browse_hrefs:
        assert f"{QUERY_KEY}={MODE_TV}" in href, f"{href!r} must retain TV mode"


def test_the_back_action_lands_on_the_tv_browse_layout(client):
    back, _ = _action_list(_tv_detail(client, SAMPLE))
    href = _attr(back, "href")
    assert href is not None
    response = client.get(href)
    assert response.status_code == 200
    assert 'class="tv-rails"' in response.get_data(as_text=True), (
        "the back action must land on the TV browse layout, not the mobile grid"
    )


def test_the_tv_control_reflects_and_names_the_saved_state(client):
    control = _control(_tv_detail(client, SAMPLE), SAMPLE["id"])
    assert _attr(control, "data-recipe-id") == SAMPLE["id"]
    assert _attr(control, "aria-label") == cookbook_control_label(
        SAMPLE["title"], False
    )
    assert _attr(control, "aria-pressed") == "false"
    assert re.search(r"(?i)save", _visible_text(control))

    assert client.post("/api/cookbook", json={"id": SAMPLE["id"]}).status_code == 201

    control = _control(_tv_detail(client, SAMPLE), SAMPLE["id"])
    assert _attr(control, "aria-label") == cookbook_control_label(SAMPLE["title"], True)
    assert _attr(control, "aria-pressed") == "true"
    assert re.search(r"(?i)saved", _visible_text(control))


def test_the_tv_and_mobile_save_controls_are_the_same_markup(client):
    tv = _control(_tv_detail(client, SAMPLE), SAMPLE["id"])
    mobile = _control(
        client.get(f"/recipe/{SAMPLE['id']}").get_data(as_text=True), SAMPLE["id"]
    )
    assert re.sub(r"\s+", " ", tv).strip() == re.sub(r"\s+", " ", mobile).strip()


def test_an_unknown_recipe_id_returns_404_in_tv_mode(client):
    assert client.get(f"/recipe/not-a-stored-recipe{TV_QUERY}").status_code == 404
