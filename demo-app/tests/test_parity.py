"""FN_TEST_PARITY: server and client search cannot drift.

There is no build step, so the recipe match predicate exists twice - once in
demo-app/recipe_search.py and once in demo-app/static/browse-logic.js. This
module owns the one shared sample-query list (mixed case, whitespace padded, one
query per searchable field, one non-matching query) and asserts that the recipe
ids GET /api/recipes?q=... returns equal the ids the shared normalisation and
containment rule leaves visible. The node browse-logic suite asserts the same
list against the client predicate, which is what closes the drift window.
"""

from __future__ import annotations

import json
from pathlib import Path

from recipe_data import load_recipes
from recipe_search import SEARCHABLE_FIELDS, filter_recipes, normalise_query, searchable_text

DEMO_APP = Path(__file__).parents[1]
NODE_PARITY_SUITE = DEMO_APP / "static" / "tests" / "parity-queries.test.js"

#: The shared sample-query list. Both suites assert this exact list.
#:   'Porridge'          - matches through the title alone, mixed case
#:   'spoonful'          - matches through the description alone
#:   'Dessert'           - matches through the category alone
#:   'Vegan'             - matches through the dietary tags alone
#:   '  almonds  '       - matches through the ingredients alone, padded
#:   '  Barley  '        - padded and mixed case together
#:   'Sourdough Starter' - matches nothing, covering the zero-result path
SHARED_QUERIES: tuple[str, ...] = (
    "Porridge",
    "spoonful",
    "Dessert",
    "Vegan",
    "  almonds  ",
    "  Barley  ",
    "Sourdough Starter",
)


def _visible_ids(recipes, query: str) -> list[str]:
    """The ids the shared normalisation and containment rule leaves visible."""
    normalised = normalise_query(query)
    return [
        recipe["id"]
        for recipe in recipes
        if not normalised or normalised in searchable_text(recipe)
    ]


def test_api_ids_equal_the_shared_rule_for_every_shared_query(client):
    recipes = list(load_recipes().recipes)

    for query in SHARED_QUERIES:
        response = client.get("/api/recipes", query_string={"q": query})
        assert response.status_code == 200, (
            f"GET /api/recipes?q={query!r} answered {response.status_code}"
        )
        served = [recipe["id"] for recipe in json.loads(response.get_data(as_text=True))]
        assert served == _visible_ids(recipes, query), (
            f"for q={query!r} the endpoint returned {served!r} but the shared rule "
            f"leaves {_visible_ids(recipes, query)!r} visible"
        )
        assert served == [recipe["id"] for recipe in filter_recipes(recipes, query)]


def test_shared_queries_cover_the_documented_cases():
    recipes = list(load_recipes().recipes)

    assert any(
        query != query.lower() and query != query.upper() for query in SHARED_QUERIES
    ), "the shared list must include a mixed-case query"
    assert any(query != query.strip() for query in SHARED_QUERIES), (
        "the shared list must include a whitespace-padded query"
    )
    assert any(not _visible_ids(recipes, query) for query in SHARED_QUERIES), (
        "the shared list must include a query that leaves no recipe visible"
    )

    for field in SEARCHABLE_FIELDS:
        assert any(
            _matches_through_field_alone(recipe, field, query)
            for query in SHARED_QUERIES
            for recipe in recipes
        ), f"the shared list must include a query that matches through {field} alone"


def _field_text(recipe, field: str) -> str:
    value = recipe[field]
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value).casefold()
    return str(value).casefold()


def _matches_through_field_alone(recipe, field: str, query: str) -> bool:
    normalised = normalise_query(query)
    if not normalised:
        return False
    others = " ".join(
        _field_text(recipe, other) for other in SEARCHABLE_FIELDS if other != field
    )
    return normalised in _field_text(recipe, field) and normalised not in others


def test_node_suite_asserts_the_same_shared_query_list():
    assert NODE_PARITY_SUITE.exists(), (
        "the node browse-logic suite must assert the shared query list so the "
        "Python and JavaScript predicates cannot drift"
    )
    suite = NODE_PARITY_SUITE.read_text(encoding="utf-8")
    for query in SHARED_QUERIES:
        assert query in suite, (
            f"the node suite must assert the shared query {query!r}"
        )
