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

from prohibited_terms import (
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
