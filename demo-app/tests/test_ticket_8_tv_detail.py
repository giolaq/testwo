"""Acceptance tests for ticket #8: the TV recipe detail page.

Scope is the TV branch of GET /recipe/<recipe_id> and the markup it renders
(MOD_TPL_TV, FN_PAGE_DETAIL, C_PAGE_DETAIL, C_SAVE_CONTROL, C_VIEW_MODE):

  * a tv-resolved detail request rendering the TV detail template
    (demo-app/templates/tv_recipe.html) from the same detail context payload
  * all nine attributes, the ingredient list in stored order and the method
    steps numbered in stored order
  * the back action and the My Cookbook action rendered as one ordered action
    list, back first, each action reachable without a pointer
  * a back href retaining mode=tv that lands on the TV browse layout
  * the TV save control producing the same state, label and cue as the mobile
    control, with its change reflected by GET /api/cookbook
  * the recipe with the most method steps still rendering both actions
  * the mobile detail route staying unchanged by the page_routes.py edit

Expected values are derived from demo-app/recipes.json through the public
loader rather than written as literals, so the assertions cannot drift from the
fixture. Everything runs offline through the create_app(testing=True) test
client from conftest.py; the cookbook API is the public seam used to flip saved
state, because the client-side toggle is not available in this gate.

Every assertion here observes public behaviour: HTTP responses and the markup
they render. Template and script sources are deliberately not read, so a missing
file surfaces as a failed behaviour assertion about the rendered page rather
than as a file-system error. The contents of static/tv-detail.js are asserted by
the companion node --test suite, which imports it through its public exports.

Deliberately NOT asserted here: TV legibility, measured contrast and the
on-screen focus treatment at 1920x1080. Those are the documented manual
reviewer checks. Nothing here freezes the absence of a later slice's routes,
scripts or capabilities.
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

BROWSE_PATH = "/"
TV_QUERY = "mode=tv"
TV_BROWSE_PATH = f"/?{TV_QUERY}"
UNKNOWN_ID = "no-such-recipe-id"

TV_DETAIL_SCRIPT = "tv-detail.js"

RAIL_NAMES = (
    "Popular this week",
    "Ready in 30 minutes",
    "Vegetarian favourites",
    "My Cookbook",
)


# --------------------------------------------------------------------------- #
# fixture access through the public loader
# --------------------------------------------------------------------------- #
def _module(name: str):
    source = DEMO_APP / f"{name}.py"
    assert source.is_file(), f"ticket #8 expects demo-app/{name}.py to exist"
    module = sys.modules.get(name)
    if module is not None and getattr(module, "__file__", None) == str(source):
        return module
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _attr(module_name: str, *candidates: str):
    module = _module(module_name)
    for candidate in candidates:
        if hasattr(module, candidate):
            return getattr(module, candidate)
    raise AssertionError(
        f"demo-app/{module_name}.py must define {' or '.join(candidates)}"
    )


def _recipes() -> list[dict]:
    recipes = list(_attr("recipe_data", "load_recipes")().recipes)
    assert recipes, "the recipe fixture must not be empty"
    return recipes


def _total_minutes(recipe: dict) -> int:
    return _attr("recipe_search", "total_minutes")(recipe)


def _sample_recipe() -> dict:
    return _recipes()[0]


def _longest_recipe() -> dict:
    """The recipe with the most method steps, then the most ingredients."""
    return max(
        _recipes(),
        key=lambda recipe: (len(recipe["steps"]), len(recipe["ingredients"])),
    )


def _no_tag_recipe() -> dict:
    for recipe in _recipes():
        if not recipe["dietary_tags"]:
            return recipe
    pytest.fail("the recipe fixture no longer contains a recipe without tags")


def _zero_cook_recipe() -> dict:
    for recipe in _recipes():
        if recipe["cook_minutes"] == 0:
            return recipe
    pytest.fail("the recipe fixture no longer contains a cook_minutes == 0 recipe")


# --------------------------------------------------------------------------- #
# HTTP and HTML helpers
# --------------------------------------------------------------------------- #
def _html(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, (
        f"GET {path} returned {response.status_code}, expected 200"
    )
    return response.get_data(as_text=True)


def _tv_detail_html(client, recipe: dict) -> str:
    return _html(client, f"/recipe/{recipe['id']}?{TV_QUERY}")


def _mobile_detail_html(client, recipe: dict) -> str:
    return _html(client, f"/recipe/{recipe['id']}")


def _text(fragment: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", without_comments)).strip()


def _attribute(markup: str, name: str) -> str | None:
    match = re.search(rf'\b{re.escape(name)}\s*=\s*"([^"]*)"', markup)
    return None if match is None else match.group(1)


def _elements(html: str) -> list[tuple[str, str, str]]:
    """(tag, attributes, inner markup) for every element, nested ones included."""
    elements: list[tuple[str, str, str]] = []
    for start in re.finditer(r"<([a-zA-Z][\w-]*)([^>]*)>", html):
        tag, attrs = start.group(1), start.group(2)
        if attrs.rstrip().endswith("/"):
            continue
        boundary = re.compile(rf"</?{re.escape(tag)}\b[^>]*>", re.IGNORECASE)
        depth = 1
        cursor = start.end()
        while depth:
            token = boundary.search(html, cursor)
            if token is None:
                break
            depth += -1 if token.group(0).startswith("</") else 1
            cursor = token.end()
            if depth == 0:
                elements.append((tag, attrs, html[start.end() : token.start()]))
    return elements


def _positions_in_order(html: str, items) -> list[int]:
    positions: list[int] = []
    cursor = 0
    for item in items:
        found = html.find(item, cursor)
        assert found != -1, (
            f"{item!r} is missing from the TV detail page, or appears out of "
            f"stored order (searched from character {cursor})"
        )
        positions.append(found)
        cursor = found + len(item)
    return positions


def _in_stored_order(fragment: str, items) -> bool:
    cursor = 0
    for item in items:
        found = fragment.find(item, cursor)
        if found == -1:
            return False
        cursor = found + len(item)
    return True


def _labelled_value(html: str, label_pattern: str, value, window: int = 160) -> bool:
    needle = re.compile(rf"\b{re.escape(str(value))}\b")
    for match in re.finditer(label_pattern, html, re.IGNORECASE):
        start = max(0, match.start() - window)
        if needle.search(html[start : match.end() + window]):
            return True
    return False


def _save_control(html: str, recipe_id: str) -> str:
    pattern = re.compile(r"<button\b[^>]*>.*?</button\s*>", re.DOTALL | re.IGNORECASE)
    controls = [
        match.group(0)
        for match in pattern.finditer(html)
        if recipe_id in match.group(0)
    ]
    assert controls, (
        "the page must expose a My Cookbook control carrying recipe id "
        f"{recipe_id!r}; found no button referencing it"
    )
    assert len(controls) == 1, (
        f"expected one My Cookbook control for {recipe_id!r}, found {len(controls)}"
    )
    return controls[0]


def _accessible_name(control: str) -> str:
    aria_label = _attribute(control, "aria-label")
    return aria_label if aria_label else _text(control)


BACK_HREF_ATTRIBUTES = ("href", "data-href", "data-back-href", "data-back")


def _back_href(markup: str) -> str | None:
    """The browse-page target carried by ``markup``, whatever attribute holds it."""
    opening = re.match(r"<[a-zA-Z][\w-]*[^>]*>", markup)
    head = opening.group(0) if opening else markup
    for name in BACK_HREF_ATTRIBUTES:
        value = _attribute(head, name)
        if value is not None and value.split("?")[0] == BROWSE_PATH:
            return value
    return None


def _back_actions(html: str) -> list[str]:
    """Elements pointing at the browse page, in render order.

    Any element carrying the browse target counts - an anchor or a control with a
    data attribute - so the assertions do not dictate how the back action is
    built, only that it exists, keeps TV mode and is keyboard reachable.
    """
    found: list[str] = []
    for tag, attrs, inner in _elements(html):
        if _back_href(f"<{tag}{attrs}>") is not None:
            found.append(f"<{tag}{attrs}>{inner}</{tag}>")
    return found


def _is_tv_browse_layout(html: str) -> bool:
    cursor = 0
    for name in RAIL_NAMES:
        found = html.find(name, cursor)
        if found == -1:
            return False
        cursor = found + len(name)
    return True


def _list_items(inner: str) -> list[str]:
    """Inner markup of the list items in ``inner``, outermost items only."""
    items = [
        item for tag, _attrs, item in _elements(inner) if tag.lower() == "li"
    ]
    return [item for item in items if not any(item in other and item != other for other in items)]


def _action_list(html: str, recipe_id: str) -> tuple[str, list[str]]:
    """The action list markup and its items: the list holding both TV actions.

    The action list is the list element that contains both the back action and
    the recipe's My Cookbook control, so the assertions do not depend on a
    particular class name.
    """
    candidates: list[tuple[str, list[str]]] = []
    for tag, attrs, inner in _elements(html):
        if tag.lower() not in {"ol", "ul"}:
            continue
        if not _back_actions(inner):
            continue
        if not re.search(
            rf'<button\b[^>]*{re.escape(recipe_id)}', inner, re.DOTALL
        ):
            continue
        candidates.append((f"<{tag}{attrs}>{inner}</{tag}>", _list_items(inner)))
    assert candidates, (
        "the TV detail page must render the back action and the My Cookbook "
        "action as one ordered action list (an <ol> or <ul> containing both), so "
        f"both are reachable without a pointer; recipe {recipe_id!r}"
    )
    # The innermost matching list is the action list itself.
    return min(candidates, key=lambda candidate: len(candidate[0]))


def _focusable(markup: str) -> bool:
    """True when the markup contains a natively focusable or tabbable element."""
    for tag, attrs, _inner in _elements(markup):
        name = tag.lower()
        tabindex = _attribute(f"<x {attrs}>", "tabindex")
        if name == "a" and _attribute(f"<x {attrs}>", "href") is not None:
            return True
        if name == "button":
            return True
        if tabindex is not None and not tabindex.strip().startswith("-"):
            return True
    return False


def _save(client, recipe: dict) -> None:
    response = client.post("/api/cookbook", json={"id": recipe["id"]})
    assert response.status_code == 201, (
        f"saving {recipe['id']!r} through POST /api/cookbook returned "
        f"{response.status_code}, expected 201"
    )


def _cookbook_ids(client) -> list[str]:
    response = client.get("/api/cookbook")
    assert response.status_code == 200
    return [saved["id"] for saved in response.get_json()]


# --------------------------------------------------------------------------- #
# The TV detail template and route branch  (C_PAGE_DETAIL, MOD_TPL_TV)
# --------------------------------------------------------------------------- #
def test_a_tv_resolved_detail_request_renders_the_tv_detail_template(client):
    """The TV branch renders the TV template, identified by its TV-only script."""
    recipe = _sample_recipe()
    html = _tv_detail_html(client, recipe)
    assert re.search(rf'<script\b[^>]*{re.escape(TV_DETAIL_SCRIPT)}', html), (
        "GET /recipe/<recipe_id>?mode=tv must render the TV detail template, "
        f"which loads demo-app/static/{TV_DETAIL_SCRIPT} as its remote-control "
        "binding; the response referenced no such script"
    )


def test_a_tv_user_agent_detail_request_also_renders_the_tv_detail_template(client):
    hints = _attr("view_mode", "TV_USER_AGENT_HINTS", "TV_HINTS", "TV_AGENT_HINTS")
    hint = list(hints)[0]
    recipe = _sample_recipe()
    response = client.get(
        f"/recipe/{recipe['id']}",
        headers={"User-Agent": f"Mozilla/5.0 ({hint}) AppleWebKit/537.36"},
    )
    assert response.status_code == 200
    assert TV_DETAIL_SCRIPT in response.get_data(as_text=True), (
        "a recognised TV user agent resolves to TV mode, so the detail route "
        "must render the TV detail template without ?mode=tv"
    )


def test_the_tv_detail_page_renders_the_shared_save_control_markup(client):
    """The rendered TV control is byte-identical to the mobile one.

    That is the observable consequence of reusing the shared save-control
    markup: the same attributes, the same visible cue, the same accessible name.
    """
    recipe = _sample_recipe()
    tv = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    mobile = _save_control(_mobile_detail_html(client, recipe), recipe["id"])
    assert re.sub(r"\s+", " ", tv) == re.sub(r"\s+", " ", mobile), (
        "the TV detail page must render the shared save-control markup so the TV "
        f"control cannot drift from the mobile one; TV rendered {tv!r} and mobile "
        f"rendered {mobile!r}"
    )


def test_the_tv_detail_page_is_sized_for_a_1920_pixel_viewport(client):
    html = _tv_detail_html(client, _sample_recipe())
    viewport = re.search(
        r'<meta\b[^>]*name\s*=\s*"viewport"[^>]*>', html, re.IGNORECASE
    )
    assert viewport is not None, "the TV detail page must declare a viewport"
    content = _attribute(viewport.group(0), "content") or ""
    assert "1920" in content, (
        "the TV detail page must be laid out for a 1920x1080 screen, like the TV "
        f"browse page; its viewport was {content!r}"
    )


# --------------------------------------------------------------------------- #
# The nine attributes  (R19, R34, C_PAGE_DETAIL)
# --------------------------------------------------------------------------- #
def test_the_tv_detail_page_shows_the_title_description_and_category(client):
    for recipe in _recipes():
        html = _tv_detail_html(client, recipe)
        assert recipe["title"] in html, f"{recipe['id']!r} must show its title"
        assert recipe["description"] in html, (
            f"{recipe['id']!r} must show its description"
        )
        assert recipe["category"] in html, (
            f"{recipe['id']!r} must show its category"
        )


def test_the_tv_detail_page_shows_every_dietary_tag(client):
    for recipe in _recipes():
        if not recipe["dietary_tags"]:
            continue
        html = _tv_detail_html(client, recipe)
        for tag in recipe["dietary_tags"]:
            assert tag in html, (
                f"{recipe['id']!r} must show its dietary tag {tag!r} on the TV "
                "detail page"
            )


def test_the_tv_detail_page_shows_prep_cook_and_total_time(client):
    for recipe in _recipes():
        html = _tv_detail_html(client, recipe)
        total = _total_minutes(recipe)
        assert _labelled_value(html, r"prep", recipe["prep_minutes"]), (
            f"{recipe['id']!r} must show its prep time of "
            f"{recipe['prep_minutes']} minutes next to a prep label"
        )
        assert _labelled_value(html, r"cook", recipe["cook_minutes"]), (
            f"{recipe['id']!r} must show its cook time of "
            f"{recipe['cook_minutes']} minutes next to a cook label"
        )
        assert _labelled_value(html, r"total", total), (
            f"{recipe['id']!r} must show its total time of {total} minutes "
            "(prep_minutes + cook_minutes) next to a total label"
        )


def test_the_tv_detail_page_shows_difficulty_and_servings(client):
    for recipe in _recipes():
        html = _tv_detail_html(client, recipe)
        assert recipe["difficulty"] in html, (
            f"{recipe['id']!r} must show its difficulty on the TV detail page"
        )
        assert _labelled_value(html, r"serv(?:es|ings?)", recipe["servings"]), (
            f"{recipe['id']!r} must show its servings value "
            f"({recipe['servings']}) next to a servings label"
        )


def test_a_zero_cook_minutes_recipe_shows_a_tv_total_time_equal_to_prep(client):
    recipe = _zero_cook_recipe()
    total = _total_minutes(recipe)
    assert total == recipe["prep_minutes"]
    html = _tv_detail_html(client, recipe)
    assert _labelled_value(html, r"total", total), (
        f"{recipe['id']!r} has cook_minutes == 0 and must still show a total "
        f"time of {total} minutes on the TV detail page"
    )
    assert _labelled_value(html, r"cook", 0), (
        f"{recipe['id']!r} must still show its cook time of 0 minutes"
    )


def test_a_recipe_without_dietary_tags_renders_no_foreign_tag_on_tv(client):
    recipe = _no_tag_recipe()
    html = _tv_detail_html(client, recipe)
    assert recipe["title"] in html
    other_tags = {tag for other in _recipes() for tag in other["dietary_tags"]}
    for tag in sorted(other_tags):
        assert not re.search(rf">\s*{re.escape(tag)}\s*<", html), (
            f"{recipe['id']!r} carries no dietary tags, so {tag!r} must not be "
            "rendered as one of its labels on the TV detail page"
        )


# --------------------------------------------------------------------------- #
# Ingredients and numbered steps  (R20, R34)
# --------------------------------------------------------------------------- #
def test_the_tv_detail_page_lists_every_ingredient_in_stored_order(client):
    for recipe in _recipes():
        html = _tv_detail_html(client, recipe)
        positions = _positions_in_order(html, recipe["ingredients"])
        assert positions == sorted(positions), (
            f"{recipe['id']!r} must list its ingredients in stored order on the "
            "TV detail page"
        )


def test_the_tv_detail_page_shows_the_steps_in_stored_order(client):
    for recipe in _recipes():
        html = _tv_detail_html(client, recipe)
        positions = _positions_in_order(html, recipe["steps"])
        assert positions == sorted(positions), (
            f"{recipe['id']!r} must show its method steps in stored order on "
            "the TV detail page"
        )


def test_the_tv_detail_page_numbers_the_method_steps(client):
    """Steps carry ordinal numbering: an ordered list, or an explicit ordinal."""
    for recipe in _recipes():
        html = _tv_detail_html(client, recipe)
        steps = recipe["steps"]
        ordered_bodies = [
            inner for tag, _attrs, inner in _elements(html) if tag.lower() == "ol"
        ]
        if any(_in_stored_order(inner, steps) for inner in ordered_bodies):
            continue
        for ordinal, step in enumerate(steps, start=1):
            index = html.find(step)
            preamble = html[max(0, index - 80) : index]
            assert re.search(rf"\b{ordinal}\b", preamble), (
                f"{recipe['id']!r} TV step {ordinal} is neither inside an "
                "ordered list containing every step in order nor preceded by "
                f"its ordinal number; markup before the step was {preamble!r}"
            )


# --------------------------------------------------------------------------- #
# The ordered action list  (R34, R35, C_TV_DETAIL_KEYS)
# --------------------------------------------------------------------------- #
def test_the_tv_detail_page_stacks_both_actions_as_one_ordered_action_list(client):
    recipe = _sample_recipe()
    _list_markup, items = _action_list(_tv_detail_html(client, recipe), recipe["id"])
    assert len(items) == 2, (
        "the TV action list must hold exactly the two primary actions (back and "
        f"My Cookbook), found {len(items)} list items"
    )


def test_the_tv_action_list_puts_the_back_action_first(client):
    recipe = _sample_recipe()
    _list_markup, items = _action_list(_tv_detail_html(client, recipe), recipe["id"])
    assert len(items) == 2, (
        "the TV action list must hold exactly the two primary actions in a fixed "
        f"order (back, then My Cookbook), found {len(items)} list items"
    )
    first, second = items[0], items[1]
    assert _back_actions(first), (
        "the first TV action must be the back action, so the pure action model's "
        f"index 0 addresses it; the first item was {_text(first)!r}"
    )
    assert re.search(rf'<button\b[^>]*{re.escape(recipe["id"])}', second, re.DOTALL), (
        "the second TV action must be the My Cookbook control for this recipe, "
        f"so index 1 addresses it; the second item was {_text(second)!r}"
    )


def test_both_tv_actions_are_reachable_without_a_pointer(client):
    recipe = _sample_recipe()
    _list_markup, items = _action_list(_tv_detail_html(client, recipe), recipe["id"])
    for index, item in enumerate(items):
        assert _focusable(item), (
            f"TV action {index} must be keyboard reachable: a link, a button or "
            f"an element with a non-negative tabindex; found {item.strip()!r}"
        )


def test_both_tv_actions_carry_visible_labels(client):
    recipe = _sample_recipe()
    _list_markup, items = _action_list(_tv_detail_html(client, recipe), recipe["id"])
    for index, item in enumerate(items):
        assert _text(item), (
            f"TV action {index} must carry visible text so a viewer can read it "
            "at television distance"
        )


def test_a_recipe_with_the_most_steps_still_renders_both_actions(client):
    recipe = _longest_recipe()
    html = _tv_detail_html(client, recipe)
    _list_markup, items = _action_list(html, recipe["id"])
    assert len(items) == 2, (
        f"{recipe['id']!r} has the most method steps of the collection "
        f"({len(recipe['steps'])}), and both primary actions must still be "
        "rendered and reachable without a pointer"
    )
    for item in items:
        assert _focusable(item)
    for step in recipe["steps"]:
        assert step in html, (
            "a long recipe must keep every method step on the TV page rather "
            "than truncating it"
        )


def test_the_tv_detail_page_keeps_ingredients_and_steps_on_the_page(client):
    recipe = _longest_recipe()
    html = _tv_detail_html(client, recipe)
    for ingredient in recipe["ingredients"]:
        assert ingredient in html, (
            f"{recipe['id']!r} must keep the ingredient {ingredient!r} on the "
            "TV detail page"
        )


# --------------------------------------------------------------------------- #
# The back action  (R22, R35, C_VIEW_MODE)
# --------------------------------------------------------------------------- #
def test_the_tv_back_action_retains_tv_mode(client):
    recipe = _sample_recipe()
    html = _tv_detail_html(client, recipe)
    actions = _back_actions(html)
    assert actions, "the TV detail page must offer a back action to browse"
    for action in actions:
        href = _back_href(action)
        assert href is not None and TV_QUERY in href, (
            f"the TV back href {href!r} must retain TV mode so Escape and "
            "Backspace return to TV browse rather than to the mobile page"
        )


def test_the_tv_back_href_lands_on_the_tv_browse_layout(client):
    recipe = _sample_recipe()
    actions = _back_actions(_tv_detail_html(client, recipe))
    assert actions, "the TV detail page must offer a back action to browse"
    href = _back_href(actions[0])
    assert _is_tv_browse_layout(_html(client, href)), (
        f"the TV back href {href!r} must land on the TV browse layout with its "
        "four rails"
    )


def test_every_tv_detail_page_offers_a_mode_preserving_back_action(client):
    for recipe in _recipes():
        actions = _back_actions(_tv_detail_html(client, recipe))
        assert actions, (
            f"the TV detail page for {recipe['id']!r} must offer a back action"
        )
        assert all(
            TV_QUERY in (_back_href(action) or "") for action in actions
        ), f"{recipe['id']!r} must keep TV mode in every browse-page link"


def test_an_unknown_recipe_id_in_tv_mode_still_returns_404(client):
    assert client.get(f"/recipe/{UNKNOWN_ID}?{TV_QUERY}").status_code == 404


# --------------------------------------------------------------------------- #
# The TV save control  (R21, R26, C_SAVE_CONTROL)
# --------------------------------------------------------------------------- #
def test_the_unsaved_tv_control_states_the_add_action_with_its_state(client):
    recipe = _sample_recipe()
    control = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    assert _accessible_name(control) == f"Add {recipe['title']} to My Cookbook"
    assert _attribute(control, "aria-pressed") == "false", (
        'the unsaved TV control must expose its state as aria-pressed="false"'
    )
    assert re.search(r"(?i)save", _text(control)), (
        "the TV control must carry a visible label, not only an accessible "
        f"name; visible text was {_text(control)!r}"
    )


def test_the_saved_tv_control_states_the_remove_action_with_a_non_colour_cue(client):
    recipe = _sample_recipe()
    _save(client, recipe)
    control = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    assert _accessible_name(control) == f"Remove {recipe['title']} from My Cookbook"
    assert _attribute(control, "aria-pressed") == "true", (
        'the saved TV control must expose its state as aria-pressed="true"'
    )
    assert re.search(r"(?i)saved", _text(control)), (
        "the saved TV control must show a visible cue that does not rely on "
        f"colour; visible text was {_text(control)!r}"
    )


def test_the_tv_control_matches_the_mobile_control_state_label_and_cue(client):
    recipe = _sample_recipe()
    tv = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    mobile = _save_control(_mobile_detail_html(client, recipe), recipe["id"])
    assert _accessible_name(tv) == _accessible_name(mobile)
    assert _attribute(tv, "aria-pressed") == _attribute(mobile, "aria-pressed")
    assert _text(tv) == _text(mobile), (
        "the TV control's visible cue must match the mobile control's; "
        f"TV showed {_text(tv)!r} and mobile showed {_text(mobile)!r}"
    )

    _save(client, recipe)

    tv = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    mobile = _save_control(_mobile_detail_html(client, recipe), recipe["id"])
    assert _attribute(tv, "aria-pressed") == "true"
    assert _accessible_name(tv) == _accessible_name(mobile), (
        "after saving, the TV and mobile controls must report the same "
        "accessible name"
    )
    assert _text(tv) == _text(mobile)


def test_the_tv_control_state_is_reflected_by_the_cookbook_endpoint(client):
    recipe = _sample_recipe()
    control = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    assert _attribute(control, "aria-pressed") == "false"
    assert recipe["id"] not in _cookbook_ids(client)

    _save(client, recipe)
    assert _cookbook_ids(client) == [recipe["id"]], (
        "the saved recipe must be reflected by GET /api/cookbook"
    )
    control = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    assert _attribute(control, "aria-pressed") == "true"

    assert client.delete(f"/api/cookbook/{recipe['id']}").status_code == 200
    assert _cookbook_ids(client) == []
    control = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    assert _attribute(control, "aria-pressed") == "false", (
        "removing the recipe must return the TV control to its unsaved state"
    )


def test_the_tv_control_carries_its_recipe_id_for_the_client_binding(client):
    recipe = _sample_recipe()
    control = _save_control(_tv_detail_html(client, recipe), recipe["id"])
    assert _attribute(control, "data-recipe-id") == recipe["id"], (
        "the TV save control must carry its recipe id so the TV binding can "
        "call the cookbook endpoints for it"
    )


# --------------------------------------------------------------------------- #
# The TV detail binding  (R35, MOD_TV_DETAIL_DOM)
# --------------------------------------------------------------------------- #
def test_the_tv_detail_script_is_served_as_a_module(client):
    """The binding is loaded as an ES module, so it can import the pure model."""
    html = _tv_detail_html(client, _sample_recipe())
    tags = re.findall(r"<script\b[^>]*>", html)
    loaders = [tag for tag in tags if TV_DETAIL_SCRIPT in tag]
    assert loaders, (
        f"the TV detail page must load demo-app/static/{TV_DETAIL_SCRIPT}; its "
        f"script tags were {tags!r}"
    )
    for tag in loaders:
        assert _attribute(tag, "type") == "module", (
            f"{TV_DETAIL_SCRIPT} must be loaded with type=\"module\", like the TV "
            "browse binding, so it can import the pure action model from "
            f"tv-logic.js; the tag was {tag!r}"
        )
    served = client.get(f"/static/{TV_DETAIL_SCRIPT}")
    assert served.status_code == 200, (
        f"demo-app/static/{TV_DETAIL_SCRIPT} must be served to the TV page; "
        f"GET /static/{TV_DETAIL_SCRIPT} returned {served.status_code}"
    )


# --------------------------------------------------------------------------- #
# The mobile detail route stays unchanged  (R19, R20, R22)
# --------------------------------------------------------------------------- #
def test_the_mobile_detail_route_still_renders_the_mobile_page(client):
    recipe = _sample_recipe()
    html = _mobile_detail_html(client, recipe)
    assert TV_DETAIL_SCRIPT not in html, (
        "the mobile recipe page must not load the TV detail script"
    )
    for name in RAIL_NAMES[:3]:
        assert name not in html, (
            f"the mobile recipe page must not render the TV rail {name!r}"
        )


def test_the_mobile_detail_back_action_returns_to_the_mobile_browse_page(client):
    recipe = _sample_recipe()
    anchors = _back_actions(_mobile_detail_html(client, recipe))
    assert anchors, "the mobile recipe page must still offer a back action"
    for anchor in anchors:
        href = _attribute(anchor, "href")
        assert href == BROWSE_PATH, (
            f"the mobile back href must be {BROWSE_PATH!r}, got {href!r}"
        )


def test_the_mobile_detail_page_still_shows_its_content_and_control(client):
    for recipe in _recipes():
        html = _mobile_detail_html(client, recipe)
        assert recipe["title"] in html
        assert recipe["description"] in html
        assert recipe["difficulty"] in html
        positions = _positions_in_order(html, recipe["ingredients"])
        assert positions == sorted(positions)
        positions = _positions_in_order(html, recipe["steps"])
        assert positions == sorted(positions)
        control = _save_control(html, recipe["id"])
        assert _attribute(control, "aria-pressed") == "false"


def test_the_mobile_browse_page_is_unaffected(client):
    html = _html(client, BROWSE_PATH)
    assert TV_DETAIL_SCRIPT not in html
    for recipe in _recipes():
        assert f'/recipe/{recipe["id"]}' in html, (
            f"the mobile browse page must still link to {recipe['id']!r}"
        )
