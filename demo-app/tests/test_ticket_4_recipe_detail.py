"""Acceptance tests for ticket #4: complete the mobile recipe detail presentation.

Scope is the rendered output of GET /recipe/<recipe_id> (MOD_TPL_MOBILE,
C_PAGE_DETAIL, C_SAVE_CONTROL, C_TOTAL_TIME):

  * the nine attributes, with values read from the loaded collection
  * the ingredient list in stored order
  * the method steps numbered and in stored order
  * the state-bearing My Cookbook control reusing the shared partial markup
  * the CSS artwork hook carrying the recipe's two colours
  * the back action to the mobile browse page
  * a recipe with no dietary_tags and a recipe with cook_minutes == 0
  * 404 for an unknown recipe id

Every expected value is derived from demo-app/recipes.json through the public
loader rather than written as a literal, so the assertions cannot drift from the
fixture. Everything runs through the create_app(testing=True) test client from
conftest.py; the cookbook API is the public seam used to flip saved state,
because the browse DOM binding belongs to a different slice.

Deliberately NOT asserted here: TV mode, view-mode resolution, rails markup and
the client-side toggle. Those belong to later slices and this file must not
freeze their absence.
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
UNKNOWN_ID = "no-such-recipe-id"

# Class-name fragments that mark a metadata label area on the detail page. Used
# only to prove such an area is never rendered empty.
LABEL_AREA_HINT = re.compile(r"(?:diet|tag|label)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# fixture access through the public loader
# --------------------------------------------------------------------------- #
def _module(name: str):
    source = DEMO_APP / f"{name}.py"
    assert source.is_file(), f"ticket #4 expects demo-app/{name}.py to exist"
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


def _recipe_with(predicate) -> dict:
    for recipe in _recipes():
        if predicate(recipe):
            return recipe
    pytest.fail("the recipe fixture no longer contains a recipe for this case")


def _sample_recipe() -> dict:
    return _recipes()[0]


def _no_tag_recipe() -> dict:
    """The no-dietary-tags boundary case (R19 / J_MOBILE_DETAIL edge case)."""
    return _recipe_with(lambda recipe: not recipe["dietary_tags"])


def _zero_cook_recipe() -> dict:
    """The cook_minutes == 0 boundary case (C_TOTAL_TIME)."""
    return _recipe_with(lambda recipe: recipe["cook_minutes"] == 0)


# --------------------------------------------------------------------------- #
# HTML helpers
# --------------------------------------------------------------------------- #
def _html(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, (
        f"GET {path} returned {response.status_code}, expected 200"
    )
    return response.get_data(as_text=True)


def _detail_html(client, recipe: dict) -> str:
    return _html(client, f"/recipe/{recipe['id']}")


def _text(fragment: str) -> str:
    """The visible text of a markup fragment, with tags and comments removed."""
    without_comments = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
    return re.sub(r"<[^>]*>", " ", without_comments).strip()


def _positions_in_order(html: str, items) -> list[int]:
    """Index of each item, each searched after the previous one, or fail."""
    positions: list[int] = []
    cursor = 0
    for item in items:
        found = html.find(item, cursor)
        assert found != -1, (
            f"{item!r} is missing from the page, or appears out of stored order "
            f"(searched from character {cursor})"
        )
        positions.append(found)
        cursor = found + len(item)
    return positions


def _in_stored_order(fragment: str, items) -> bool:
    """True when every item appears in ``fragment`` in the given order."""
    cursor = 0
    for item in items:
        found = fragment.find(item, cursor)
        if found == -1:
            return False
        cursor = found + len(item)
    return True


def _labelled_value(html: str, label_pattern: str, value, window: int = 120) -> bool:
    """True when ``value`` appears within ``window`` characters of the label."""
    needle = re.compile(rf"\b{re.escape(str(value))}\b")
    for match in re.finditer(label_pattern, html, re.IGNORECASE):
        start = max(0, match.start() - window)
        if needle.search(html[start : match.end() + window]):
            return True
    return False


def _elements(html: str) -> list[tuple[str, str, str]]:
    """(tag, attributes, inner markup) for every element, nested ones included.

    Nesting is respected by counting same-name start tags, so an element's inner
    markup is the text up to its own closing tag rather than the first one.
    """
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


def _ordered_list_bodies(html: str) -> list[str]:
    return [inner for tag, _attrs, inner in _elements(html) if tag.lower() == "ol"]


def _save_control(html: str, recipe_id: str) -> str:
    """The My Cookbook control markup for one recipe, taken from the page."""
    pattern = re.compile(
        r"<button\b[^>]*>.*?</button\s*>", re.DOTALL | re.IGNORECASE
    )
    controls = [
        match.group(0)
        for match in pattern.finditer(html)
        if recipe_id in match.group(0)
    ]
    assert controls, (
        f"the page must expose a My Cookbook control carrying recipe id "
        f"{recipe_id!r}; found no button referencing it"
    )
    assert len(controls) == 1, (
        f"expected one My Cookbook control for {recipe_id!r}, found {len(controls)}"
    )
    return controls[0]


def _attribute(markup: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', markup)
    return None if match is None else match.group(1)


def _accessible_name(control: str) -> str:
    """The control's accessible name: aria-label if present, else its text."""
    aria_label = _attribute(control, "aria-label")
    if aria_label:
        return aria_label
    return _text(control)


def _save(client, recipe: dict) -> None:
    response = client.post("/api/cookbook", json={"id": recipe["id"]})
    assert response.status_code == 201, (
        f"saving {recipe['id']!r} through POST /api/cookbook returned "
        f"{response.status_code}, expected 201"
    )


# --------------------------------------------------------------------------- #
# The nine attributes  (R19, C_PAGE_DETAIL)
# --------------------------------------------------------------------------- #
def test_detail_page_shows_the_title_description_and_category(client):
    for recipe in _recipes():
        html = _detail_html(client, recipe)
        assert recipe["title"] in html, f"{recipe['id']!r} must show its title"
        assert recipe["description"] in html, (
            f"{recipe['id']!r} must show its description"
        )
        assert recipe["category"] in html, f"{recipe['id']!r} must show its category"


def test_detail_page_shows_every_dietary_tag(client):
    for recipe in _recipes():
        if not recipe["dietary_tags"]:
            continue
        html = _detail_html(client, recipe)
        for tag in recipe["dietary_tags"]:
            assert tag in html, (
                f"{recipe['id']!r} must show its dietary tag {tag!r}"
            )


def test_detail_page_shows_difficulty_and_servings(client):
    for recipe in _recipes():
        html = _detail_html(client, recipe)
        assert recipe["difficulty"] in html, (
            f"{recipe['id']!r} must show its difficulty"
        )
        assert _labelled_value(html, r"serv(?:es|ings?)", recipe["servings"]), (
            f"{recipe['id']!r} must show its servings value "
            f"({recipe['servings']}) next to a servings label"
        )


def test_detail_page_shows_prep_cook_and_total_time(client):
    for recipe in _recipes():
        html = _detail_html(client, recipe)
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


# --------------------------------------------------------------------------- #
# Ingredients and steps  (R20, C_PAGE_DETAIL)
# --------------------------------------------------------------------------- #
def test_detail_page_lists_every_ingredient_in_stored_order(client):
    for recipe in _recipes():
        html = _detail_html(client, recipe)
        positions = _positions_in_order(html, recipe["ingredients"])
        assert positions == sorted(positions), (
            f"{recipe['id']!r} must list its ingredients in stored order"
        )


def test_detail_page_shows_the_steps_in_stored_order(client):
    for recipe in _recipes():
        html = _detail_html(client, recipe)
        positions = _positions_in_order(html, recipe["steps"])
        assert positions == sorted(positions), (
            f"{recipe['id']!r} must show its method steps in stored order"
        )


def test_detail_page_numbers_the_method_steps(client):
    """Steps carry ordinal numbering: an ordered list, or an explicit ordinal."""
    for recipe in _recipes():
        html = _detail_html(client, recipe)
        steps = recipe["steps"]

        if any(_in_stored_order(inner, steps) for inner in _ordered_list_bodies(html)):
            continue

        for ordinal, step in enumerate(steps, start=1):
            index = html.find(step)
            preamble = html[max(0, index - 80) : index]
            assert re.search(rf"\b{ordinal}\b", preamble), (
                f"{recipe['id']!r} step {ordinal} is neither inside an ordered "
                "list containing every step in order nor preceded by its ordinal "
                f"number; markup before the step was {preamble!r}"
            )


# --------------------------------------------------------------------------- #
# The My Cookbook control  (R21, R26, C_SAVE_CONTROL)
# --------------------------------------------------------------------------- #
def test_detail_control_names_the_recipe_and_states_the_add_action(client):
    recipe = _sample_recipe()
    control = _save_control(_detail_html(client, recipe), recipe["id"])

    name = _accessible_name(control)
    assert name == f"Add {recipe['title']} to My Cookbook", (
        "an unsaved recipe's control must have the accessible name "
        f"'Add {recipe['title']} to My Cookbook', got {name!r}"
    )
    assert _attribute(control, "aria-pressed") == "false", (
        "the unsaved control must expose its state as aria-pressed=\"false\""
    )
    assert re.search(r"(?i)save", _text(control)), (
        "the control must carry a visible label, not only an accessible name; "
        f"visible text was {_text(control)!r}"
    )


def test_detail_control_states_the_remove_action_once_the_recipe_is_saved(client):
    recipe = _sample_recipe()
    _save(client, recipe)

    control = _save_control(_detail_html(client, recipe), recipe["id"])
    name = _accessible_name(control)
    assert name == f"Remove {recipe['title']} from My Cookbook", (
        "a saved recipe's control must have the accessible name "
        f"'Remove {recipe['title']} from My Cookbook', got {name!r}"
    )
    assert _attribute(control, "aria-pressed") == "true", (
        "the saved control must expose its state as aria-pressed=\"true\""
    )
    assert re.search(r"(?i)saved", _text(control)), (
        "the saved control must show a visible saved cue that does not rely on "
        f"colour; visible text was {_text(control)!r}"
    )


def test_detail_control_state_comes_from_the_same_boolean_as_the_browse_cards(client):
    """One saved-state boolean drives both surfaces, so they cannot disagree."""
    recipe = _sample_recipe()

    detail = _save_control(_detail_html(client, recipe), recipe["id"])
    card = _save_control(_html(client, BROWSE_PATH), recipe["id"])
    assert _accessible_name(detail) == _accessible_name(card)
    assert _attribute(detail, "aria-pressed") == _attribute(card, "aria-pressed")

    _save(client, recipe)

    detail = _save_control(_detail_html(client, recipe), recipe["id"])
    card = _save_control(_html(client, BROWSE_PATH), recipe["id"])
    assert _attribute(detail, "aria-pressed") == "true"
    assert _accessible_name(detail) == _accessible_name(card), (
        "after saving, the detail control and the browse card control must "
        "report the same accessible name"
    )


def test_detail_control_reuses_the_shared_save_control_partial(client):
    """The control markup is the shared partial, not a second copy."""
    partial = DEMO_APP / "templates" / "_partials" / "save_control.html"
    assert partial.is_file(), (
        "the shared My Cookbook control partial must live at "
        "demo-app/templates/_partials/save_control.html"
    )
    template = (DEMO_APP / "templates" / "recipe.html").read_text(encoding="utf-8")
    assert "_partials/save_control.html" in template, (
        "recipe.html must include the shared save-control partial rather than "
        "duplicating the control markup"
    )

    recipe = _sample_recipe()
    control = _save_control(_detail_html(client, recipe), recipe["id"])
    assert _attribute(control, "data-recipe-id") == recipe["id"], (
        "the rendered control must carry its recipe id for the client binding"
    )


# --------------------------------------------------------------------------- #
# Artwork hook and the back action  (R22, C_CARD_ARTWORK)
# --------------------------------------------------------------------------- #
def test_detail_page_exposes_both_recipe_colours_as_css_custom_properties(client):
    for recipe in _recipes():
        html = _detail_html(client, recipe)
        for color in recipe["colors"]:
            assert re.search(rf"--[a-z-]+:\s*{re.escape(color)}", html), (
                f"{recipe['id']!r} must expose colour {color!r} as a CSS custom "
                "property so the artwork needs no network image"
            )


def test_detail_back_action_returns_to_the_mobile_browse_page(client):
    recipe = _sample_recipe()
    html = _detail_html(client, recipe)
    anchors = re.findall(r"<a\b[^>]*>.*?</a\s*>", html, re.DOTALL | re.IGNORECASE)
    back = [
        anchor
        for anchor in anchors
        if _attribute(anchor, "href") == BROWSE_PATH
    ]
    assert back, (
        "the recipe page must offer a back action whose href is the mobile "
        f"browse path {BROWSE_PATH!r}"
    )
    assert any(_text(anchor) for anchor in back), (
        "the back action must carry visible text"
    )
    assert client.get(BROWSE_PATH).status_code == 200


# --------------------------------------------------------------------------- #
# Boundary cases  (J_MOBILE_DETAIL edge cases, C_TOTAL_TIME)
# --------------------------------------------------------------------------- #
def test_a_recipe_with_no_dietary_tags_renders_no_empty_label_area(client):
    recipe = _no_tag_recipe()
    html = _detail_html(client, recipe)

    assert recipe["title"] in html, (
        "a recipe with no dietary tags must still render its content"
    )
    assert recipe["category"] in html, (
        "the category must still be shown when there are no dietary tags"
    )

    for tag, attrs, inner in _elements(html):
        class_attr = _attribute(f"<x {attrs}>", "class") or ""
        if not LABEL_AREA_HINT.search(class_attr):
            continue
        assert _text(inner), (
            f"{recipe['id']!r} has no dietary tags, so the empty "
            f"<{tag} class=\"{class_attr}\"> label area must not be rendered"
        )


def test_a_recipe_with_no_dietary_tags_shows_no_tag_from_another_recipe(client):
    recipe = _no_tag_recipe()
    html = _detail_html(client, recipe)
    other_tags = {
        tag for other in _recipes() for tag in other["dietary_tags"]
    }
    for tag in sorted(other_tags):
        assert not re.search(rf">\s*{re.escape(tag)}\s*<", html), (
            f"{recipe['id']!r} carries no dietary tags, so {tag!r} must not be "
            "rendered as one of its labels"
        )


def test_a_recipe_with_zero_cook_minutes_shows_a_total_time_equal_to_prep(client):
    recipe = _zero_cook_recipe()
    assert recipe["cook_minutes"] == 0
    total = _total_minutes(recipe)
    assert total == recipe["prep_minutes"], (
        "with cook_minutes == 0 the derived total time must equal prep_minutes"
    )

    html = _detail_html(client, recipe)
    assert _labelled_value(html, r"total", total), (
        f"{recipe['id']!r} has cook_minutes == 0 and must still show a total "
        f"time of {total} minutes"
    )
    assert _labelled_value(html, r"cook", 0), (
        f"{recipe['id']!r} must still show its cook time of 0 minutes"
    )


# --------------------------------------------------------------------------- #
# Failure path  (R23, C_PAGE_DETAIL)
# --------------------------------------------------------------------------- #
def test_an_unknown_recipe_id_still_returns_404(client):
    assert client.get(f"/recipe/{UNKNOWN_ID}").status_code == 404


def test_an_unknown_recipe_id_returns_404_even_with_a_recipe_shaped_id(client):
    known = _sample_recipe()["id"]
    assert client.get(f"/recipe/{known}-not-a-recipe").status_code == 404
