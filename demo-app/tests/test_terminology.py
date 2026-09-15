"""C_TERM_GUARD: the terminology and partial-rebrand guard (R1, R5, R40, R45).

FN_TEST_TERM_GUARD drives FN_TERM_SURFACES over both modes of both pages, all
six supported endpoints and the 404 body, the template and static sources, the
client fetch targets and both test roots, then asserts zero matches of the single
prohibited-term pattern through FN_TERM_SCAN.

Scope, exclusions and the reason test sources are held to R40 rather than to a
literal term scan are documented once in ``prohibited_terms``. The pattern is
tuned for precision only - never by dropping a term, never by shortening the
surface list - and this module never weakens, skips or otherwise defers a failure.
"""

from __future__ import annotations

import json
import re

import pytest

from prohibited_terms import (
    CINEMA_ERA_FILES,
    DOCUMENTED_EXCLUSIONS,
    PROHIBITED_TERMS,
    SCANNED_SURFACES,
    assert_no_cinema_dependency,
    assert_terms_absent,
    collect_surfaces,
    first_recipe_id,
    is_test_source_surface,
    json_keys,
    prohibited_pattern,
)

# Both modes of both pages, and every supported endpoint, must be scanned. The
# guard fails if any of these labels stops appearing in the collected surface.
EXPECTED_SURFACE_MARKERS = (
    "GET / (mobile)",
    "GET /?mode=tv (tv)",
    "?mode=tv (tv)",
    "GET /api/recipes",
    "GET /api/cookbook",
    "POST /api/cookbook",
    "DELETE /api/cookbook/",
    "GET /api/rails",
    "404 body",
    # The saved branch renders the "Remove <title> from My Cookbook" accessible
    # name and the populated My Cookbook rail, so it must be scanned too.
    "GET / (mobile, saved)",
    "GET /?mode=tv (tv, saved)",
    "?mode=tv (tv, saved)",
    "GET /api/rails (saved)",
    "source templates/browse.html",
    "source templates/tv_browse.html",
    "source static/styles.css",
    "client fetch targets in static/browse.js",
    "test source tests/test_app.py",
)


def test_terminology_guard_reports_zero_matches(client):
    """FN_TEST_TERM_GUARD: the whole supported surface is clean."""
    surfaces = collect_surfaces(client)
    assert surfaces, "collect_surfaces() must return the surfaces to scan"

    scanned = 0
    for surface, text in surfaces:
        if is_test_source_surface(surface):
            assert_no_cinema_dependency(text, surface)
        else:
            assert_terms_absent(text, surface)
        scanned += 1

    assert scanned == len(surfaces)


def test_guard_covers_both_modes_both_pages_and_all_six_endpoints(client):
    labels = " | ".join(surface for surface, _ in collect_surfaces(client))
    recipe_id = first_recipe_id()

    for path in ("/", "/?mode=tv", f"/recipe/{recipe_id}", f"/recipe/{recipe_id}?mode=tv"):
        assert path in labels, f"the guard must scan {path}"
    for marker in EXPECTED_SURFACE_MARKERS:
        assert marker in labels, f"the guard must scan {marker}"

    # The documented exclusions really are excluded.
    assert ".git" not in labels, "the guard must never inspect Git history"
    assert "prd" not in labels.casefold(), "the guard must never inspect the PRD"
    assert "recipes.json" not in labels, (
        "internal non-public filenames are out of scope per R5"
    )


def test_the_saved_state_branch_is_actually_scanned(client):
    """The saved accessible name and populated cookbook rail are covered.

    A saved-state pass that rendered the empty cookbook again would satisfy the
    surface labels while leaving the branch unscanned, so this asserts the text
    really differs: the saved control label and the saved recipe both appear.
    """
    recipe_id = first_recipe_id()
    surfaces = dict(collect_surfaces(client))

    saved_page = surfaces["GET / (mobile, saved)"]
    assert "Remove " in saved_page and "from My Cookbook" in saved_page, (
        "the saved-state pass must render the saved accessible name, which is "
        "only produced when the cookbook is not empty"
    )
    assert "Add " in surfaces["GET / (mobile)"]

    saved_rails = json.loads(surfaces["GET /api/rails (saved)"])
    cookbook = [rail for rail in saved_rails if rail["name"] == "My Cookbook"]
    assert cookbook and cookbook[0]["recipe_ids"] == [recipe_id], (
        "the saved-state pass must render a populated My Cookbook rail"
    )
    empty_rails = json.loads(surfaces["GET /api/rails"])
    assert [r for r in empty_rails if r["name"] == "My Cookbook"][0]["recipe_ids"] == []

    # The store is left exactly as it was found, so the guard stays deterministic.
    assert client.get("/api/cookbook").get_json() == []


def test_public_json_keys_and_the_404_body_are_recipe_domain(client):
    pattern = prohibited_pattern()
    recipe_id = first_recipe_id()

    saved = client.post("/api/cookbook", json={"id": recipe_id})
    assert saved.status_code == 201
    removed = client.delete(f"/api/cookbook/{recipe_id}")
    assert removed.status_code == 200

    for label, payload in (
        ("GET /api/recipes", client.get("/api/recipes").get_json()),
        (f"GET /api/recipes/{recipe_id}", client.get(f"/api/recipes/{recipe_id}").get_json()),
        ("GET /api/cookbook", client.get("/api/cookbook").get_json()),
        ("GET /api/rails", client.get("/api/rails").get_json()),
        ("POST /api/cookbook", saved.get_json()),
        (f"DELETE /api/cookbook/{recipe_id}", removed.get_json()),
    ):
        for key in sorted(json_keys(payload)):
            assert not pattern.search(key), (
                f"{label} exposes the prohibited public JSON key {key!r}"
            )

    missing = client.get("/api/recipes/not-a-recipe")
    assert missing.status_code == 404
    assert missing.get_json() == {"error": "Recipe not found"}
    assert_terms_absent(missing.get_data(as_text=True), "GET /api/recipes/not-a-recipe")


def test_page_metadata_is_recipe_domain(client):
    """Titles and meta descriptions are page metadata, in scope for R5."""
    recipe_id = first_recipe_id()
    for path in ("/", "/?mode=tv", f"/recipe/{recipe_id}", f"/recipe/{recipe_id}?mode=tv"):
        html = client.get(path).get_data(as_text=True)
        metadata = re.findall(r"<title>(.*?)</title>", html, re.DOTALL) + re.findall(
            r"<meta[^>]*>", html
        )
        assert metadata, f"{path} must render page metadata"
        for item in metadata:
            assert_terms_absent(item, f"page metadata of {path}")


def test_cinema_era_files_and_dependencies_stay_gone():
    """R40: no test passes because a movie endpoint or film fixture survived."""
    for path in CINEMA_ERA_FILES:
        assert not path.exists(), f"the cinema-era file {path} must stay deleted"


def test_the_pattern_is_the_single_frozen_vocabulary():
    pattern = prohibited_pattern()
    assert len(PROHIBITED_TERMS) == 10
    assert pattern.flags & re.IGNORECASE

    for term in PROHIBITED_TERMS:
        for variant in (term, term.upper(), term.lower(), term.title()):
            assert pattern.search(f"rendered copy with {variant} in it"), (
                f"the pattern must match {variant!r}"
            )

    for marked_up in (
        'class="movie-card"',
        "<title>Pocket Cinema</title>",
        "#watchlist",
        '{"movie_ids": []}',
        "--paper-poster",
        # An upper-case letter ends a term too, so the camelCase identifiers a
        # partial rebrand leaves behind in the client modules or a class hook
        # cannot slip past the boundary.
        "movieCard",
        "watchlistToggle",
        "posterUrl",
        "filmTitle",
        "cinemaMode",
    ):
        assert pattern.search(marked_up), f"the pattern must match {marked_up!r}"

    # Precision, never by dropping a term: innocent substrings must not block.
    for innocent in (
        "upcoming",
        "topcoat",
        "filmography",
        "cinematography",
        "moviegoer",
        "posterior",
        "generating a recipe collection",
    ):
        assert not pattern.search(innocent), f"false positive on {innocent!r}"


def test_the_guard_fails_with_the_term_the_surface_and_the_excerpt():
    """Negative control: a reintroduced term must fail usably for a reviewer.

    Exercised on synthetic surface text so the repository itself is never
    committed in a failing state; the same assertion is what a local
    reintroduction into a template or a JSON key hits.
    """
    assert assert_terms_absent("Good food, clearly told. 13 recipes", "GET /") is None

    surface = "GET / (mobile)"
    template_like = '<article class="movie-card" data-recipe-id="golden-oat-porridge">'
    with pytest.raises(AssertionError) as excinfo:
        assert_terms_absent(template_like, surface)
    message = str(excinfo.value)
    assert "movie" in message.casefold()
    assert surface in message
    assert "recipe-card" not in message
    assert "<article class=" in message and "data-recipe-id" in message, (
        "the excerpt must surround the match so the failure is reviewer evidence"
    )

    with pytest.raises(AssertionError) as excinfo:
        assert_terms_absent(json.dumps({"movie_ids": ["afterlight"]}), "GET /api/rails")
    assert "GET /api/rails" in str(excinfo.value)


def test_an_unreachable_surface_fails_rather_than_being_skipped(client):
    class _Broken:
        status_code = 500

        def get_data(self, as_text: bool = False):
            return "" if as_text else b""

    class _BrokenClient:
        def __init__(self, wrapped, broken_path):
            self._wrapped = wrapped
            self._broken = broken_path

        def get(self, path, *args, **kwargs):
            if str(path).split("?")[0] == self._broken:
                return _Broken()
            return self._wrapped.get(path, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

    for broken_path in ("/", "/api/recipes", "/api/rails"):
        with pytest.raises(AssertionError):
            collect_surfaces(_BrokenClient(client, broken_path))


def test_test_sources_are_held_to_the_documented_r40_rule():
    surface = "test source tests/test_example.py"
    assert (
        assert_no_cinema_dependency(
            '        ("GET", "/api/watchlist"),\n    assert "#watchlist" not in html\n',
            surface,
        )
        is None
    ), "a negative assertion naming a removed path is required coverage, not a leftover"

    with pytest.raises(AssertionError) as excinfo:
        assert_no_cinema_dependency("from catalog.json import data\n", surface)
    assert "catalog.json" in str(excinfo.value)

    with pytest.raises(AssertionError):
        assert_no_cinema_dependency(
            "import {matchesMovie} from '../app-logic.js';\n", surface
        )


def test_scope_and_exclusions_are_documented_once():
    assert len(SCANNED_SURFACES) >= 7
    for excluded in ("Git history", "the PRD"):
        assert excluded in DOCUMENTED_EXCLUSIONS
