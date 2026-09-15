"""C_TERM_GUARD: the terminology and partial-rebrand guard.

Runs inside the existing pytest gate. It drives the Flask test client over both
modes of both pages and over every supported endpoint, reads the template,
static and test sources plus the client fetch targets, and asserts zero
case-insensitive, word-boundary matches of the prohibited terms.

The guard is never skipped and never xfailed: a red guard is the signal that a
partial rebrand survived somewhere on the supported surface. Git history and the
PRD are excluded surfaces and are never inspected. Internal, non-public
filenames and pre-existing internal identifiers are out of scope per the human
decision recorded in R5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prohibited_terms import (
    LEGACY_PATHS,
    PROHIBITED_TERMS,
    assert_no_live_legacy_paths,
    assert_terms_absent,
    collect_surfaces,
    prohibited_pattern,
    scannable_source,
    suite_sources,
)


def test_no_cinema_terms_on_the_supported_surface(client):
    """FN_TEST_TERM_GUARD: zero matches over every collected surface."""
    surfaces = collect_surfaces(client)
    assert len(surfaces) >= 10, (
        f"the guard collected only {len(surfaces)} surfaces; it must cover both "
        "modes of both pages, every supported endpoint and the sources"
    )
    for surface, text in surfaces:
        assert_terms_absent(text, surface)


def test_no_test_source_depends_on_a_removed_cinema_path():
    """A test may name a removed path only while asserting it is gone."""
    sources = suite_sources()
    assert sources, "the guard must find the test sources to scan"
    for path in sources:
        assert_no_live_legacy_paths(path, scannable_source(path))


def test_the_guard_scans_both_pages_in_both_modes_with_a_recipe_saved(client):
    """Saved-state output is a surface too, not only the empty cookbook."""
    labels = [surface for surface, _ in collect_surfaces(client)]
    for expected in (
        "GET / (mobile browse page) with a saved recipe",
        "GET /?mode=tv (TV browse rails) with a saved recipe",
        "GET /api/cookbook with a saved recipe",
    ):
        assert expected in labels, f"the guard never scanned {expected}"
    assert any(
        "recipe detail) with a saved recipe" in label for label in labels
    ), "the guard never scanned a recipe detail page with a saved recipe"
    assert client.get("/api/cookbook").get_json() == [], (
        "collect_surfaces must leave the cookbook empty again so it cannot "
        "leak saved state into other assertions"
    )


@pytest.mark.parametrize(
    "symbol",
    [
        "nextWatchlist", "addToWatchlist", "matchesMovie", "getMovieIds",
        "showPoster", "watchlistToggle", "movie_ids", "MovieCard", "--poster-bg",
    ],
)
def test_the_pattern_catches_a_term_anywhere_in_an_identifier(symbol):
    """A prohibited term in the tail of a camel-case symbol is still a match."""
    assert prohibited_pattern().search(symbol) is not None, symbol


@pytest.mark.parametrize(
    "word", ["upcoming", "operating", "posterior", "specification", "integrating"]
)
def test_the_pattern_leaves_innocent_host_words_alone(word):
    assert prohibited_pattern().search(word) is None, word


def test_absence_evidence_is_scoped_to_the_statement_that_names_the_path():
    """One '404' elsewhere in a file must not excuse a live legacy request."""
    gone = LEGACY_PATHS[1]
    must_not_be_requested = LEGACY_PATHS[2]
    source = (
        "def test_legacy_routes_are_gone(client):\n"
        f"    assert client.get('{gone}').status_code == 404\n"
        "\n"
        "def test_browse_lists_saved_recipes(client):\n"
        f"    body = client.get('{must_not_be_requested}').get_data(as_text=True)\n"
    )
    with pytest.raises(AssertionError) as failure:
        assert_no_live_legacy_paths(Path("synthetic_test.py"), source)
    assert must_not_be_requested in str(failure.value)
    assert "synthetic_test.py:5" in str(failure.value)


def test_guard_reports_a_reintroduced_term_in_markup_and_in_a_json_key():
    """Negative control: the guard fails with usable reviewer evidence."""
    pattern = prohibited_pattern()
    for term in PROHIBITED_TERMS:
        markup = f'<h1 class="{term}-card">Spiced Plum Galette</h1>'
        payload = json.dumps({f"{term}_ids": ["golden-oat-porridge"]})
        for text, surface in (
            (markup, "GET / (mobile browse page)"),
            (payload, "GET /api/rails"),
        ):
            assert pattern.search(text) is not None
            try:
                assert_terms_absent(text, surface)
            except AssertionError as failure:
                message = str(failure)
                assert term.casefold() in message.casefold()
                assert surface in message
                assert "Galette" in message or "golden-oat-porridge" in message
            else:  # pragma: no cover - the guard must not stay silent
                raise AssertionError(
                    f"the guard stayed silent about the reintroduced term {term!r}"
                )
