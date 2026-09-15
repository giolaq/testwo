"""View-mode resolution, TV template selection and TV rail rendering.

Covers resolver precedence, TV user-agent detection, the unrecognised-value
fallback, TV browse template selection, TV link retention, rail rendering with
the two-recipe floor, and the My Cookbook rail reflecting a saved recipe after a
refresh. Everything runs offline through the create_app(testing=True) client.
"""

from __future__ import annotations

import re

import pytest

from rails import COOKBOOK_EMPTY_STATE, RAIL_NAMES
from recipe_data import load_recipes
from view_mode import TV_USER_AGENT_HINTS, is_tv_user_agent, mode_url, resolve_view_mode

TV_QUERY = "mode=tv"
TV_BROWSE_PATH = "/?mode=tv"

PHONE_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
TV_AGENT = f"Mozilla/5.0 ({TV_USER_AGENT_HINTS[0]}) AppleWebKit/537.36"

TV_MODE = {"mode": "tv", "source": "query"}
MOBILE_MODE = {"mode": "mobile", "source": "default"}


def _html(client, path: str, user_agent: str | None = None) -> str:
    headers = {} if user_agent is None else {"User-Agent": user_agent}
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _rail_segments(html: str) -> list[str]:
    """The markup following each rail heading, in rail order."""
    starts = []
    cursor = 0
    for name in RAIL_NAMES:
        found = html.find(f">{name}<", cursor)
        assert found != -1, f"rail heading {name!r} is missing after character {cursor}"
        starts.append(found)
        cursor = found + len(name)
    bounds = starts + [len(html)]
    return [html[bounds[i] : bounds[i + 1]] for i in range(len(RAIL_NAMES))]


def _card_ids(fragment: str) -> list[str]:
    ids: list[str] = []
    for value in re.findall(r'data-recipe-id="([^"]*)"', fragment):
        if value not in ids:
            ids.append(value)
    return ids


# --------------------------------------------------------------------------- #
# Resolver precedence and user-agent detection
# --------------------------------------------------------------------------- #
def test_an_explicit_tv_query_resolves_to_tv_from_the_query():
    assert resolve_view_mode("tv", None) == {"mode": "tv", "source": "query"}


def test_a_tv_user_agent_resolves_to_tv_without_a_query():
    assert resolve_view_mode(None, TV_AGENT) == {"mode": "tv", "source": "user_agent"}


def test_an_explicit_tv_query_beats_a_phone_user_agent():
    assert resolve_view_mode("tv", PHONE_AGENT)["mode"] == "tv"


@pytest.mark.parametrize("value", ["", "TV-ish", "banana", "desktop", None])
def test_an_unrecognised_mode_value_falls_back_to_mobile_by_default(value):
    assert resolve_view_mode(value, None) == {"mode": "mobile", "source": "default"}


@pytest.mark.parametrize("hint", TV_USER_AGENT_HINTS)
def test_tv_user_agent_detection_is_case_insensitive(hint):
    for variant in (hint, hint.upper(), hint.lower()):
        assert is_tv_user_agent(f"Mozilla/5.0 ({variant})") is True


def test_tv_user_agent_detection_rejects_none_and_a_phone():
    assert is_tv_user_agent(None) is False
    assert is_tv_user_agent(PHONE_AGENT) is False


# --------------------------------------------------------------------------- #
# Mode-preserving URLs
# --------------------------------------------------------------------------- #
def test_mode_url_retains_tv_mode_and_leaves_mobile_paths_alone():
    assert mode_url("/", TV_MODE) == "/?mode=tv"
    assert mode_url("/recipe/golden-oat-porridge", TV_MODE) == (
        "/recipe/golden-oat-porridge?mode=tv"
    )
    assert mode_url("/?a=1", TV_MODE) == "/?a=1&mode=tv"
    assert mode_url("/?mode=tv", TV_MODE) == "/?mode=tv"
    assert mode_url("/", MOBILE_MODE) == "/"


# --------------------------------------------------------------------------- #
# TV template selection and link retention
# --------------------------------------------------------------------------- #
def test_the_tv_query_selects_the_tv_rails_template(client):
    html = _html(client, TV_BROWSE_PATH)
    for name in RAIL_NAMES:
        assert f">{name}<" in html


def test_a_tv_user_agent_selects_the_tv_template_without_the_query(client):
    assert ">Popular this week<" in _html(client, "/", TV_AGENT)


def test_the_default_browse_page_is_the_mobile_layout(client):
    html = _html(client, "/?mode=banana", PHONE_AGENT)
    assert ">Popular this week<" not in html
    assert "All recipes" in html


def test_tv_card_and_back_links_retain_tv_mode(client):
    hrefs = re.findall(r'href="(/recipe/[^"]*)"', _html(client, TV_BROWSE_PATH))
    assert hrefs
    assert all(TV_QUERY in href for href in hrefs)

    recipe_id = load_recipes().recipes[0]["id"]
    detail = _html(client, f"/recipe/{recipe_id}?{TV_QUERY}")
    back = [h for h in re.findall(r'href="([^"]*)"', detail) if h.split("?")[0] == "/"]
    assert back and all(TV_QUERY in href for href in back)


# --------------------------------------------------------------------------- #
# Rail rendering
# --------------------------------------------------------------------------- #
def test_every_non_cookbook_rail_renders_at_least_two_cards(client):
    segments = _rail_segments(_html(client, TV_BROWSE_PATH))
    for index, name in enumerate(RAIL_NAMES[:3]):
        assert len(_card_ids(segments[index])) >= 2, name


def test_the_empty_cookbook_rail_shows_the_recipe_domain_empty_state(client):
    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[3]
    assert _card_ids(segment) == []
    assert COOKBOOK_EMPTY_STATE in segment


def test_the_cookbook_rail_reflects_a_saved_recipe_after_a_refresh(client):
    recipe_id = load_recipes().recipes[0]["id"]
    assert client.post("/api/cookbook", json={"id": recipe_id}).status_code == 201

    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[3]
    assert _card_ids(segment) == [recipe_id]
    assert COOKBOOK_EMPTY_STATE not in segment

    assert client.delete(f"/api/cookbook/{recipe_id}").status_code == 200
    segment = _rail_segments(_html(client, TV_BROWSE_PATH))[3]
    assert _card_ids(segment) == []


def test_tv_cards_carry_their_rail_and_card_indices(client):
    segments = _rail_segments(_html(client, TV_BROWSE_PATH))
    for index in range(3):
        cards = re.findall(
            r'data-rail-index="(\d+)"\s+data-card-index="(\d+)"', segments[index]
        )
        assert cards
        assert [rail for rail, _ in cards] == [str(index)] * len(cards)
        assert [card for _, card in cards] == [str(i) for i in range(len(cards))]
