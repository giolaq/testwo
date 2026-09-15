"""FN_TEST_PARITY: server and client search must agree (C_SEARCH_PY/JS, R15, R18).

One shared sample-query list - mixed case, whitespace padded, one query per
searchable field, one non-matching query and the empty query - is run through
``GET /api/recipes?q=...`` and compared with the ids the shared normalisation and
containment rule leaves visible. The same list is asserted client-side by the
node browse-logic suite over the search text the server renders into each card,
so the Python and JavaScript predicates cannot drift; there is no build step that
could share the code itself, so this test is the seam that holds them equal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from recipe_data import load_recipes
from recipe_search import (
    SEARCHABLE_FIELDS,
    filter_recipes,
    normalise_query,
    searchable_text,
)

DEMO_APP = Path(__file__).parents[1]
NODE_TEST_ROOT = DEMO_APP / "static" / "tests"

# The shared sample-query list. Each entry names the searchable field it probes
# so a reviewer can see the coverage, and the node suite asserts the identical
# queries and the identical expected ids.
SAMPLE_QUERIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("title", "weeknight", ("weeknight-salmon-traybake",)),
    ("description", "warm start to the day", ("golden-oat-porridge",)),
    (
        "category",
        "DESSERT",
        ("dark-chocolate-mousse", "honey-roast-plums", "no-bake-peanut-oat-bars"),
    ),
    (
        "dietary_tags",
        " vegan",
        (
            "sunrise-berry-smoothie-bowl",
            "lemon-chickpea-salad",
            "slow-simmered-lentil-stew",
            "spiced-butternut-curry",
            "no-bake-peanut-oat-bars",
        ),
    ),
    ("ingredients", "GARLIC", ("slow-simmered-lentil-stew",)),
    ("title", "  Lemon Chickpea  ", ("lemon-chickpea-salad",)),
    ("none", "pineapple pizza", ()),
    (
        "all",
        "",
        (
            "golden-oat-porridge",
            "herb-garden-omelette",
            "sunrise-berry-smoothie-bowl",
            "lemon-chickpea-salad",
            "tomato-basil-toastie",
            "smoked-paprika-chicken-wraps",
            "slow-simmered-lentil-stew",
            "weeknight-salmon-traybake",
            "mushroom-barley-risotto",
            "spiced-butternut-curry",
            "dark-chocolate-mousse",
            "honey-roast-plums",
            "no-bake-peanut-oat-bars",
        ),
    ),
)


def _shared_rule_ids(query: str) -> list[str]:
    """The ids the shared normalisation and containment rule leaves visible."""
    folded = normalise_query(query)
    return [
        recipe["id"]
        for recipe in load_recipes().recipes
        if not folded or folded in searchable_text(recipe)
    ]


def test_the_shared_query_list_covers_every_field_padding_and_a_miss():
    fields = {field for field, _, _ in SAMPLE_QUERIES}
    for field in SEARCHABLE_FIELDS:
        assert field in fields, f"the shared list must include a {field} query"
    assert any(query != query.strip() for _, query, _ in SAMPLE_QUERIES)
    assert any(
        query.strip() and query != query.lower() for _, query, _ in SAMPLE_QUERIES
    )
    assert any(not expected for _, _, expected in SAMPLE_QUERIES)


@pytest.mark.parametrize(
    "field,query,expected_ids",
    SAMPLE_QUERIES,
    ids=[f"{field}:{query.strip() or 'empty'}" for field, query, _ in SAMPLE_QUERIES],
)
def test_search_parity_between_server_and_client(client, field, query, expected_ids):
    response = client.get("/api/recipes", query_string={"q": query})
    assert response.status_code == 200
    api_ids = [recipe["id"] for recipe in response.get_json()]

    assert api_ids == list(expected_ids), (
        f"GET /api/recipes?q={query!r} returned {api_ids}, expected {list(expected_ids)}"
    )
    assert api_ids == _shared_rule_ids(query), (
        f"GET /api/recipes?q={query!r} disagrees with the shared containment rule"
    )
    assert api_ids == [
        recipe["id"] for recipe in filter_recipes(load_recipes().recipes, query)
    ]


def test_browse_cards_carry_the_search_text_the_api_filters_on(client):
    """The client filters the text the server produced, so parity is structural."""
    collection = load_recipes()
    html = client.get("/").get_data(as_text=True)
    rendered = dict(
        re.findall(r'data-recipe-id="([^"]+)"\s+data-search-text="([^"]*)"', html)
    )
    assert len(rendered) == len(collection.recipes)
    for recipe in collection.recipes:
        actual = rendered[recipe["id"]].replace("&#34;", '"').replace("&amp;", "&")
        assert actual == searchable_text(recipe)


def test_the_node_suite_asserts_the_same_shared_query_list():
    """The identical list must be asserted against the client predicate."""
    suites = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(NODE_TEST_ROOT.glob("*.test.js"))
    }
    assert suites, "the node browse-logic suite must exist"

    carriers = []
    for name, text in suites.items():
        if all(query in text for _, query, _ in SAMPLE_QUERIES if query.strip()):
            carriers.append((name, text))
    assert carriers, (
        "a node browse-logic suite must assert the shared sample-query list so the "
        "Python and JavaScript predicates cannot drift"
    )

    for name, text in carriers:
        for _, query, expected_ids in SAMPLE_QUERIES:
            for recipe_id in expected_ids:
                assert recipe_id in text, (
                    f"{name} must assert {recipe_id!r} for the shared query {query!r}"
                )
