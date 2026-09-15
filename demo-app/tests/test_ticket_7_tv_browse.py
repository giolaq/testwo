"""Acceptance tests for ticket #7: TV mode entry, curated rails, remote focus.

Scope (C_VIEW_MODE, C_PAGE_BROWSE, C_PAGE_DETAIL, C_RAILS, C_SAVE_CONTROL):

  * demo-app/view_mode.py: resolve_view_mode precedence, TV user-agent
    detection, unrecognised-value fallback, mode_url link retention, and the
    module staying Flask-free
  * GET / selecting the TV rails template for ?mode=tv and for a recognised TV
    user-agent hint, and falling back to the mobile layout otherwise
  * demo-app/templates/tv_browse.html: the four rails in fixed order with their
    exact names, the two-recipe floor on every non-cookbook rail, focusable
    cards carrying rail-index and card-index data attributes, mode-preserving
    hrefs, the shared card partial, and the recipe-domain empty state for an
    empty My Cookbook rail
  * the My Cookbook rail reflecting the saved collection after a refresh, and
    becoming empty again after a delete and a refresh
  * detail requests in TV mode still rendering successfully with a
    mode-preserving back href

Expected values are derived from demo-app/recipes.json through the public
loader and from the public rail composer, so the assertions cannot drift from
the fixture. Everything runs offline through the create_app(testing=True) test
client from conftest.py.

Deliberately NOT asserted here: which template the TV detail route selects.
T-TVDETAIL owns that choice, so this file only requires the detail route to
answer 200 with a mode-preserving back href, and never freezes the absence of a
TV detail template or of the TV detail script.
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
TV_BROWSE_PATH = "/?mode=tv"
TV_QUERY = "mode=tv"

RAIL_NAMES = (
    "Popular this week",
    "Ready in 30 minutes",
    "Vegetarian favourites",
    "My Cookbook",
)
COOKBOOK_RAIL_INDEX = 3

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


# --------------------------------------------------------------------------- #
# module and fixture access through public seams
# --------------------------------------------------------------------------- #
def _module(name: str):
    source = DEMO_APP / f"{name}.py"
    assert source.is_file(), (
        f"ticket #7 expects demo-app/{name}.py to exist as the single "
        "Flask-free view-mode resolver"
    )
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


def _resolve_view_mode(query_mode, user_agent):
    return _attr("view_mode", "resolve_view_mode")(query_mode, user_agent)


def _is_tv_user_agent(user_agent):
    return _attr("view_mode", "is_tv_user_agent")(user_agent)


def _mode_url(path: str, view_mode):
    return _attr("view_mode", "mode_url")(path, view_mode)


def _tv_mode():
    return _resolve_view_mode("tv", None)


def _mobile_mode():
    return _resolve_view_mode(None, None)


def _tv_user_agent_hints() -> list[str]:
    """The module's single TV user-agent hint constant, whatever it is named.

    The hint list is required to be one module constant, so the tests read it
    instead of hard-coding user-agent strings in several places.
    """
    module = _module("view_mode")
    candidates: list[tuple[str, list[str]]] = []
    for name in dir(module):
        if name.startswith("_") or not name.isupper():
            continue
        value = getattr(module, name)
        if isinstance(value, (list, tuple, frozenset, set, dict)) and value:
            items = list(value)
            values = [item for item in items if isinstance(item, str) and item.strip()]
            if len(values) == len(items):
                candidates.append((name, values))
    assert candidates, (
        "demo-app/view_mode.py must define the recognised TV user-agent hints "
        "as a single module-level constant sequence of strings"
    )
    hints = [
        values
        for _name, values in candidates
        if all(_is_tv_user_agent(f"Mozilla/5.0 ({value})") for value in values)
    ]
    assert hints, (
        "no module-level constant in demo-app/view_mode.py holds strings that "
        "is_tv_user_agent() recognises; the hint list must be that one constant. "
        f"Constants inspected: {[name for name, _ in candidates]}"
    )
    return hints[0]


def _recipes() -> list[dict]:
    recipes = list(_attr("recipe_data", "load_recipes")().recipes)
    assert recipes, "the recipe fixture must not be empty"
    return recipes


def _collection():
    return _attr("recipe_data", "load_recipes")()


def _expected_rails(saved_ids=()) -> list[dict]:
    return _attr("rails", "build_rails")(_collection(), list(saved_ids))


def _cookbook_empty_state() -> str:
    return _attr("rails", "COOKBOOK_EMPTY_STATE")


def _sample_recipe() -> dict:
    """A recipe that is not already a member of the derived cookbook rail."""
    return _recipes()[0]


# --------------------------------------------------------------------------- #
# HTML helpers
# --------------------------------------------------------------------------- #
def _get(client, path: str, user_agent: str | None = None):
    headers = {} if user_agent is None else {"User-Agent": user_agent}
    return client.get(path, headers=headers)


def _html(client, path: str, user_agent: str | None = None) -> str:
    response = _get(client, path, user_agent)
    assert response.status_code == 200, (
        f"GET {path} returned {response.status_code}, expected 200"
    )
    return response.get_data(as_text=True)


def _text(fragment: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", without_comments)).strip()


def _visible_position(html: str, needle: str, start: int) -> int:
    """First index of ``needle`` at or after ``start`` that sits in element text.

    Occurrences inside a start tag (an attribute value such as an accessible
    label) are skipped, so a rail name only counts where a viewer would read it.
    """
    cursor = start
    while True:
        found = html.find(needle, cursor)
        if found == -1:
            return -1
        inside_tag = html.rfind("<", 0, found) > html.rfind(">", 0, found)
        if not inside_tag:
            return found
        cursor = found + 1


def _is_tv_layout(html: str) -> bool:
    """True when every rail name is rendered as text, in the fixed rail order."""
    cursor = 0
    for name in RAIL_NAMES:
        found = _visible_position(html, name, cursor)
        if found == -1:
            return False
        cursor = found + len(name)
    return True


def _rail_segments(html: str) -> list[str]:
    """The markup of each rail, split at its rendered rail name, in order."""
    starts: list[int] = []
    cursor = 0
    for name in RAIL_NAMES:
        found = _visible_position(html, name, cursor)
        assert found != -1, (
            f"the TV browse page must render the rail name {name!r} as visible "
            f"text after the preceding rails; searched from character {cursor}"
        )
        starts.append(found)
        cursor = found + len(name)
    bounds = starts + [len(html)]
    return [html[bounds[index] : bounds[index + 1]] for index in range(len(RAIL_NAMES))]


def _tags_with(fragment: str, attribute: str) -> list[tuple[str, str]]:
    """(tag name, attribute markup) for every start tag carrying ``attribute``."""
    found: list[tuple[str, str]] = []
    for match in re.finditer(r"<([a-zA-Z][\w-]*)([^>]*)>", fragment):
        if re.search(rf"\b{re.escape(attribute)}\s*=", match.group(2)):
            found.append((match.group(1).lower(), match.group(2)))
    return found


def _attribute(markup: str, name: str) -> str | None:
    match = re.search(rf'\b{re.escape(name)}\s*=\s*"([^"]*)"', markup)
    return None if match is None else match.group(1)


def _values(fragment: str, attribute: str) -> list[str]:
    return [
        value
        for value in (
            _attribute(attrs, attribute) for _tag, attrs in _tags_with(fragment, attribute)
        )
        if value is not None
    ]


def _card_ids(fragment: str) -> list[str]:
    """Recipe ids of the cards in ``fragment``, in render order, once each.

    A card may repeat its recipe id on more than one element (the card itself
    and its save control), so identity is what matters here, not the count.
    """
    seen: list[str] = []
    for value in _values(fragment, "data-recipe-id"):
        if value not in seen:
            seen.append(value)
    return seen


def _detail_hrefs(fragment: str) -> list[str]:
    return [
        href
        for href in re.findall(r'href\s*=\s*"([^"]*)"', fragment)
        if href.startswith("/recipe/")
    ]


def _save(client, recipe: dict) -> None:
    response = client.post("/api/cookbook", json={"id": recipe["id"]})
    assert response.status_code == 201, (
        f"saving {recipe['id']!r} through POST /api/cookbook returned "
        f"{response.status_code}, expected 201"
    )


def _unsave(client, recipe: dict) -> None:
    response = client.delete(f"/api/cookbook/{recipe['id']}")
    assert response.status_code == 200, (
        f"removing {recipe['id']!r} through DELETE /api/cookbook returned "
        f"{response.status_code}, expected 200"
    )


# --------------------------------------------------------------------------- #
# The resolver  (R30, C_VIEW_MODE, FN_RESOLVE_VIEW_MODE)
# --------------------------------------------------------------------------- #
def test_view_mode_module_is_flask_free():
    module = DEMO_APP / "view_mode.py"
    assert module.is_file(), (
        "ticket #7 must add demo-app/view_mode.py as the single view-mode resolver"
    )
    source = module.read_text(encoding="utf-8")
    assert not re.search(r"(?i)\bflask\b", source), (
        "demo-app/view_mode.py must stay Flask-free so the resolver is "
        "unit-testable from plain arguments"
    )


def test_an_explicit_tv_query_resolves_to_tv_mode_from_the_query():
    resolved = _resolve_view_mode("tv", None)
    assert resolved["mode"] == "tv"
    assert resolved["source"] == "query", (
        "an explicit mode=tv must report source 'query', got "
        f"{resolved['source']!r}"
    )


def test_a_recognised_tv_user_agent_resolves_to_tv_mode_without_a_query():
    for hint in _tv_user_agent_hints():
        resolved = _resolve_view_mode(None, f"Mozilla/5.0 ({hint}) AppleWebKit/537.36")
        assert resolved["mode"] == "tv", (
            f"the recognised TV hint {hint!r} must resolve to TV mode without "
            "the query parameter"
        )
        assert resolved["source"] == "user_agent", (
            f"the hint {hint!r} must report source 'user_agent', got "
            f"{resolved['source']!r}"
        )


def test_an_explicit_tv_query_wins_over_a_mobile_user_agent():
    resolved = _resolve_view_mode("tv", MOBILE_USER_AGENT)
    assert resolved["mode"] == "tv", (
        "an explicit mode=tv must win over a mobile user agent"
    )
    assert resolved["source"] == "query"


def test_an_unrecognised_mode_value_falls_back_to_mobile_with_source_default():
    for value in ["", "TV-ish", "banana", "desktop", "tv2", "0"]:
        resolved = _resolve_view_mode(value, None)
        assert resolved["mode"] == "mobile", (
            f"the unrecognised mode value {value!r} must fall back to mobile"
        )
        assert resolved["source"] == "default", (
            f"the unrecognised mode value {value!r} must report source "
            f"'default', got {resolved['source']!r}"
        )


def test_no_mode_and_no_hint_resolves_to_mobile_by_default():
    resolved = _resolve_view_mode(None, MOBILE_USER_AGENT)
    assert resolved["mode"] == "mobile"
    assert resolved["source"] == "default"


def test_tv_user_agent_detection_is_case_insensitive():
    for hint in _tv_user_agent_hints():
        for variant in (hint, hint.upper(), hint.lower(), hint.swapcase()):
            assert _is_tv_user_agent(f"Mozilla/5.0 ({variant}) Safari/537.36") is True, (
                f"is_tv_user_agent must match the hint {hint!r} regardless of "
                f"case; {variant!r} was not recognised"
            )


def test_tv_user_agent_detection_rejects_none_and_a_mobile_agent():
    assert _is_tv_user_agent(None) is False, (
        "is_tv_user_agent(None) must return False rather than raising"
    )
    assert _is_tv_user_agent("") is False
    assert _is_tv_user_agent(MOBILE_USER_AGENT) is False, (
        "a phone user agent must not be recognised as a TV hint"
    )


# --------------------------------------------------------------------------- #
# Mode-preserving URLs  (R22, FN_MODE_URL)
# --------------------------------------------------------------------------- #
def test_mode_url_appends_tv_mode_in_tv_mode():
    tv = _tv_mode()
    for path in ["/", "/recipe/golden-oat-porridge"]:
        url = _mode_url(path, tv)
        assert url.startswith(path), (
            f"mode_url({path!r}) must keep the path, got {url!r}"
        )
        assert TV_QUERY in url, (
            f"mode_url({path!r}) must retain TV mode, got {url!r}"
        )


def test_mode_url_returns_the_path_unchanged_in_mobile_mode():
    mobile = _mobile_mode()
    for path in ["/", "/recipe/golden-oat-porridge"]:
        assert _mode_url(path, mobile) == path, (
            f"mode_url({path!r}) in mobile mode must return the path unchanged"
        )


# --------------------------------------------------------------------------- #
# TV template selection  (R30, C_PAGE_BROWSE)
# --------------------------------------------------------------------------- #
def test_the_tv_query_renders_the_tv_layout(client):
    assert _is_tv_layout(_html(client, TV_BROWSE_PATH)), (
        "GET /?mode=tv must render the TV rails layout with the four rail "
        "names in their fixed order"
    )


def test_a_recognised_tv_user_agent_renders_the_tv_layout_without_the_query(client):
    for hint in _tv_user_agent_hints():
        html = _html(client, BROWSE_PATH, f"Mozilla/5.0 ({hint}) AppleWebKit/537.36")
        assert _is_tv_layout(html), (
            f"a request carrying the recognised TV hint {hint!r} must render "
            "the TV layout without ?mode=tv"
        )


def test_the_tv_query_wins_over_a_mobile_user_agent_on_the_browse_page(client):
    assert _is_tv_layout(_html(client, TV_BROWSE_PATH, MOBILE_USER_AGENT)), (
        "an explicit mode=tv must render the TV layout even for a phone user agent"
    )


def test_an_unrecognised_mode_value_renders_the_mobile_layout(client):
    html = _html(client, "/?mode=banana", MOBILE_USER_AGENT)
    assert not _is_tv_layout(html), (
        "an unrecognised mode value must fall back to the mobile layout, not "
        "render the TV rails"
    )
    for name in RAIL_NAMES[:3]:
        assert name not in html, (
            f"the mobile browse page must not render the TV rail {name!r}"
        )


def test_the_default_mobile_browse_page_keeps_plain_hrefs(client):
    html = _html(client, BROWSE_PATH)
    hrefs = _detail_hrefs(html)
    assert hrefs, "the mobile browse page must still link to recipe pages"
    for href in hrefs:
        assert TV_QUERY not in href, (
            f"a mobile browse card must not carry TV mode in its href: {href!r}"
        )


# --------------------------------------------------------------------------- #
# The four rails  (R31, C_RAILS, MOD_TPL_TV)
# --------------------------------------------------------------------------- #
def test_the_tv_page_renders_the_four_rails_in_fixed_order_with_exact_names(client):
    html = _html(client, TV_BROWSE_PATH)
    positions = []
    cursor = 0
    for name in RAIL_NAMES:
        found = html.find(name, cursor)
        assert found != -1, (
            f"the TV browse page must render the rail name {name!r} exactly, "
            f"after the preceding rails; searched from character {cursor}"
        )
        positions.append(found)
        cursor = found + len(name)
    assert positions == sorted(positions)


def test_every_non_cookbook_rail_renders_at_least_two_recipe_cards(client):
    segments = _rail_segments(_html(client, TV_BROWSE_PATH))
    for index, name in enumerate(RAIL_NAMES[:COOKBOOK_RAIL_INDEX]):
        card_ids = _card_ids(segments[index])
        assert len(card_ids) >= 2, (
            f"the rail {name!r} must render at least two recipe cards, found "
            f"{len(card_ids)}: {card_ids}"
        )


def test_rail_membership_matches_the_derived_rail_composition(client):
    segments = _rail_segments(_html(client, TV_BROWSE_PATH))
    expected = _expected_rails()
    for index, rail in enumerate(expected):
        assert rail["name"] == RAIL_NAMES[index]
        rendered = _card_ids(segments[index])
        assert rendered == list(rail["recipe_ids"]), (
            f"the rail {rail['name']!r} must render the derived recipe ids in "
            f"order; expected {list(rail['recipe_ids'])}, rendered {rendered}"
        )


def test_rail_cards_carry_their_rail_index_and_sequential_card_index(client):
    segments = _rail_segments(_html(client, TV_BROWSE_PATH))
    for index, name in enumerate(RAIL_NAMES):
        rail_indices = _values(segments[index], "data-rail-index")
        card_indices = _values(segments[index], "data-card-index")
        card_count = len(_card_ids(segments[index]))
        if card_count == 0:
            continue
        assert card_indices == [str(position) for position in range(card_count)], (
            f"the cards of rail {name!r} must carry data-card-index values "
            f"0..{card_count - 1} in order, found {card_indices}"
        )
        assert rail_indices, (
            f"the cards of rail {name!r} must carry a data-rail-index attribute"
        )
        assert set(rail_indices) == {str(index)}, (
            f"every card of rail {name!r} must carry data-rail-index="
            f"\"{index}\", found {sorted(set(rail_indices))}"
        )


def test_rail_cards_are_focusable(client):
    """A card carries a tabindex, or contains the anchor that receives focus."""
    html = _html(client, TV_BROWSE_PATH)
    tags = _tags_with(html, "data-card-index")
    assert tags, "the TV browse page must render cards carrying data-card-index"
    for tag, attrs in tags:
        focusable = tag == "a" or _attribute(attrs, "tabindex") is not None
        if focusable:
            continue
        start = html.find(f"<{tag}{attrs}>")
        window = html[start : start + 800]
        assert re.search(r"<a\b[^>]*href", window) or "tabindex" in window, (
            f"the card element <{tag}> carrying data-card-index must be "
            "focusable: it needs a tabindex, or must contain the anchor that "
            "receives focus"
        )


def test_every_rail_card_href_retains_tv_mode(client):
    html = _html(client, TV_BROWSE_PATH)
    hrefs = _detail_hrefs(html)
    assert hrefs, "the TV browse page must link every card to its recipe page"
    for href in hrefs:
        assert TV_QUERY in href, (
            f"the TV card href {href!r} must retain TV mode so Enter opens the "
            "recipe in TV mode"
        )


def test_a_rail_card_href_opens_the_recipe_successfully(client):
    html = _html(client, TV_BROWSE_PATH)
    href = _detail_hrefs(html)[0]
    assert _get(client, href).status_code == 200, (
        f"the TV Enter target {href!r} must resolve to a rendered recipe page"
    )


def test_the_tv_template_reuses_the_shared_card_partial(client):
    template = DEMO_APP / "templates" / "tv_browse.html"
    assert template.is_file(), (
        "ticket #7 must add demo-app/templates/tv_browse.html"
    )
    source = template.read_text(encoding="utf-8")
    assert "_partials/recipe_card.html" in source, (
        "tv_browse.html must include the shared recipe card partial so the "
        "save-control contract cannot drift between modes"
    )

    recipe_id = _card_ids(_rail_segments(_html(client, TV_BROWSE_PATH))[0])[0]
    html = _html(client, TV_BROWSE_PATH)
    control = re.search(
        rf'<button\b[^>]*data-recipe-id="{re.escape(recipe_id)}"[^>]*>',
        html,
    )
    assert control is not None, (
        f"the TV card for {recipe_id!r} must render the shared My Cookbook "
        "control carrying its recipe id"
    )
    assert _attribute(control.group(0), "aria-pressed") in {"true", "false"}, (
        "the TV save control must expose its saved state as aria-pressed"
    )


# --------------------------------------------------------------------------- #
# The My Cookbook rail  (R36, C_RAILS, FN_BUILD_RAILS)
# --------------------------------------------------------------------------- #
def test_an_empty_cookbook_rail_shows_the_recipe_domain_empty_state(client):
    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[COOKBOOK_RAIL_INDEX]
    assert _card_ids(segment) == [], (
        "nothing is saved yet, so the My Cookbook rail must render no cards"
    )
    empty_state = _cookbook_empty_state()
    assert empty_state in _text(segment), (
        f"the empty My Cookbook rail must show the recipe-domain empty state "
        f"{empty_state!r}; rendered text was {_text(segment)!r}"
    )


def test_a_saved_recipe_appears_in_the_cookbook_rail_after_a_refresh(client):
    recipe = _sample_recipe()
    _save(client, recipe)

    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[COOKBOOK_RAIL_INDEX]
    assert _card_ids(segment) == [recipe["id"]], (
        f"after POST /api/cookbook and a TV refresh, {recipe['id']!r} must "
        "appear in the My Cookbook rail"
    )
    assert recipe["title"] in segment, (
        "the My Cookbook rail must render the saved recipe's card, not only its id"
    )
    assert _cookbook_empty_state() not in _text(segment), (
        "the My Cookbook rail must drop its empty state once a recipe is saved"
    )


def test_a_removed_recipe_is_absent_from_the_cookbook_rail_after_a_refresh(client):
    recipe = _sample_recipe()
    _save(client, recipe)
    _unsave(client, recipe)

    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[COOKBOOK_RAIL_INDEX]
    assert _card_ids(segment) == [], (
        f"after DELETE /api/cookbook/{recipe['id']} and a TV refresh, the My "
        "Cookbook rail must be empty again"
    )
    assert _cookbook_empty_state() in _text(segment)


def test_the_cookbook_rail_reflects_saved_order_after_a_refresh(client):
    first, second = _recipes()[0], _recipes()[1]
    _save(client, second)
    _save(client, first)

    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[COOKBOOK_RAIL_INDEX]
    assert _card_ids(segment) == [second["id"], first["id"]], (
        "the My Cookbook rail must reflect the saved collection in saved order"
    )


def test_the_cookbook_rail_cards_are_indexed_from_zero(client):
    recipe = _sample_recipe()
    _save(client, recipe)

    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[COOKBOOK_RAIL_INDEX]
    assert _values(segment, "data-card-index") == ["0"]
    assert set(_values(segment, "data-rail-index")) == {str(COOKBOOK_RAIL_INDEX)}, (
        "a saved card in the My Cookbook rail must carry data-rail-index="
        f"\"{COOKBOOK_RAIL_INDEX}\" so vertical focus moves address it"
    )


# --------------------------------------------------------------------------- #
# Detail requests in TV mode  (R22, C_PAGE_DETAIL)
# --------------------------------------------------------------------------- #
def test_a_detail_request_in_tv_mode_renders_successfully(client):
    for recipe in _recipes():
        response = _get(client, f"/recipe/{recipe['id']}?{TV_QUERY}")
        assert response.status_code == 200, (
            f"GET /recipe/{recipe['id']}?{TV_QUERY} returned "
            f"{response.status_code}, expected 200"
        )


def test_a_detail_page_in_tv_mode_has_a_mode_preserving_back_href(client):
    recipe = _sample_recipe()
    html = _html(client, f"/recipe/{recipe['id']}?{TV_QUERY}")
    hrefs = re.findall(r'href\s*=\s*"([^"]*)"', html)
    back = [href for href in hrefs if href.split("?")[0] == BROWSE_PATH]
    assert back, "the TV detail page must offer a back action to the browse page"
    assert all(TV_QUERY in href for href in back), (
        "every browse-page link on a TV detail page must retain TV mode; found "
        f"{back}"
    )
    assert _is_tv_layout(_html(client, back[0])), (
        f"the TV back href {back[0]!r} must land on the TV browse layout"
    )


def test_a_detail_request_in_tv_mode_still_returns_404_for_an_unknown_recipe(client):
    assert _get(client, f"/recipe/no-such-recipe-id?{TV_QUERY}").status_code == 404


def test_a_detail_request_with_a_tv_user_agent_keeps_tv_mode_in_its_back_href(client):
    recipe = _sample_recipe()
    hint = _tv_user_agent_hints()[0]
    html = _html(
        client,
        f"/recipe/{recipe['id']}",
        f"Mozilla/5.0 ({hint}) AppleWebKit/537.36",
    )
    hrefs = [
        href
        for href in re.findall(r'href\s*=\s*"([^"]*)"', html)
        if href.split("?")[0] == BROWSE_PATH
    ]
    assert hrefs, "the detail page must offer a back action to the browse page"
    assert all(TV_QUERY in href for href in hrefs), (
        "a TV user-agent detail request must keep TV mode in its back href so "
        f"the viewer returns to TV browse; found {hrefs}"
    )


# --------------------------------------------------------------------------- #
# TV client wiring  (R32, R33, MOD_TV_BROWSE_DOM)
# --------------------------------------------------------------------------- #
def test_the_tv_browse_page_loads_the_tv_browse_script(client):
    script = DEMO_APP / "static" / "tv-browse.js"
    assert script.is_file(), (
        "ticket #7 must add demo-app/static/tv-browse.js as the TV browse DOM "
        "binding"
    )
    html = _html(client, TV_BROWSE_PATH)
    assert "tv-browse.js" in html, (
        "the TV browse page must load demo-app/static/tv-browse.js"
    )


def test_the_tv_browse_binding_delegates_to_the_pure_focus_model():
    binding = DEMO_APP / "static" / "tv-browse.js"
    assert binding.is_file(), "ticket #7 must add demo-app/static/tv-browse.js"
    source = binding.read_text(encoding="utf-8")
    assert "tv-logic.js" in source, (
        "tv-browse.js must import the pure focus model from tv-logic.js rather "
        "than deciding focus transitions itself"
    )
    assert "scrollIntoView" in source, (
        "tv-browse.js must scroll the focused card into view on every move"
    )
    assert TV_QUERY not in source, (
        "tv-browse.js must open the server-rendered href rather than "
        "re-deriving TV mode in JavaScript"
    )
