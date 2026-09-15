"""Acceptance tests for ticket #6, server side of the save-control contract.

The client behaviour of ticket #6 is asserted in
``demo-app/static/tests/ticket-6-browse-client.test.js``. This module owns the
two halves that only the server can prove:

* the shared expected label list, asserted here against ``FN_SAVE_CONTROL_LABEL``
  (``cookbook_control_label``) and in the Node suite against ``FN_JS_SAVE_LABEL``,
  which is what holds the two implementations equal (acceptance criterion 6);
* that a save made through the supported cookbook endpoints is reflected by
  ``GET /api/cookbook`` (acceptance criterion 3), and that the browse client
  module exists and names no URL outside the two supported cookbook paths
  (acceptance criterion 4).

Everything runs offline through the Flask test client and the committed fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from page_routes import browse_context, cookbook_control_label, detail_context
from recipe_data import load_recipes

DEMO_APP = Path(__file__).parents[1]
BROWSE_CLIENT = DEMO_APP / "static" / "browse.js"
BROWSE_LOGIC = DEMO_APP / "static" / "browse-logic.js"

# The identical list lives in demo-app/static/tests/ticket-6-browse-client.test.js
# as SAVE_LABEL_CASES. Both suites assert the same strings, so the server-rendered
# label and the client-rewritten label cannot drift.
SAVE_LABEL_CASES = [
    ("Golden Oat Porridge", False, "Add Golden Oat Porridge to My Cookbook"),
    ("Golden Oat Porridge", True, "Remove Golden Oat Porridge from My Cookbook"),
    ("Lemon Chickpea Salad", False, "Add Lemon Chickpea Salad to My Cookbook"),
    ("Lemon Chickpea Salad", True, "Remove Lemon Chickpea Salad from My Cookbook"),
    ("Tomato and Basil Toastie", False, "Add Tomato and Basil Toastie to My Cookbook"),
    ("Tomato and Basil Toastie", True, "Remove Tomato and Basil Toastie from My Cookbook"),
]


@pytest.mark.parametrize("title,saved,expected", SAVE_LABEL_CASES)
def test_save_control_label_matches_the_shared_expected_strings(title, saved, expected):
    assert cookbook_control_label(title, saved) == expected


def test_rendered_controls_use_the_shared_label_wording():
    """The label the server renders is the one the client has to reproduce."""
    collection = load_recipes()
    recipe = collection.recipes[0]

    class _Store:
        def list(self):
            return []

        def __contains__(self, recipe_id):
            return False

    store = _Store()
    card = next(
        card
        for card in browse_context(collection, store)["cards"]
        if card["recipe"]["id"] == recipe["id"]
    )
    assert card["control_label"] == f"Add {recipe['title']} to My Cookbook"
    assert detail_context(recipe, store)["control_label"] == card["control_label"]


def test_save_and_remove_are_reflected_by_get_api_cookbook(client):
    collection = load_recipes()
    recipe_id = collection.recipes[2]["id"]

    assert client.get("/api/cookbook").get_json() == []

    created = client.post("/api/cookbook", json={"id": recipe_id})
    assert created.status_code == 201

    saved = client.get("/api/cookbook").get_json()
    assert [entry["id"] for entry in saved] == [recipe_id]
    assert saved[0]["title"] == collection.by_id[recipe_id]["title"]

    assert client.delete(f"/api/cookbook/{recipe_id}").status_code == 200
    assert client.get("/api/cookbook").get_json() == []


def test_browse_client_module_exists():
    assert BROWSE_CLIENT.is_file(), (
        "ticket #6 must add demo-app/static/browse.js as the thin browse binding"
    )


def test_browse_client_names_only_the_supported_cookbook_urls():
    assert BROWSE_CLIENT.is_file(), "demo-app/static/browse.js must exist"
    source = BROWSE_CLIENT.read_text(encoding="utf-8")

    paths = set(re.findall(r"/api/[A-Za-z0-9_./<>{}$-]*", source))
    unexpected = {
        path for path in paths if not re.fullmatch(r"/api/cookbook(/.*)?", path)
    }
    assert not unexpected, f"the client must not name these URLs: {sorted(unexpected)}"


def test_browse_logic_exports_the_remaining_pure_helpers():
    source = BROWSE_LOGIC.read_text(encoding="utf-8")
    for name in ("nextCookbook", "matchCountLabel", "emptyStateVisible", "saveControlState"):
        assert re.search(rf"export function {name}\b", source), (
            f"browse-logic.js must export {name}() for ticket #6"
        )
