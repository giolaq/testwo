"""Shared prohibited-terminology definitions for the TableStory guard.

This module owns the frozen term sequence, the single compiled pattern, the
scan that turns a match into reviewer evidence, and the collection of surfaces
the guard drives. Every guard assertion imports these definitions instead of
restating them, so tightening the pattern is one edit.

Surfaces scanned (the supported customer-visible and public surface):

  * GET / and GET /recipe/<recipe_id> in both mobile and TV mode - the whole
    rendered response, including page metadata and accessible labels
  * all six supported JSON endpoints plus the unknown-recipe error body
  * the client fetch targets named by the browse and TV scripts
  * the template sources, the static sources and the test sources

Documented exclusions (per the human decision recorded in R5, and R40):

  * Git history and the PRD are never inspected; this module reads only the
    application sources through the filesystem and the Flask test client.
  * Internal, non-public filenames and pre-existing internal identifiers are
    out of scope: renaming them is explicitly not required.
  * Source comments, docstrings and Jinja/CSS/JS comment blocks are stripped
    before a source file is scanned. They are not customer-visible output, not
    public field names and not names of anything.
  * In test sources only, string literals are stripped as well, so what the
    guard asserts there is the identifier surface - test names, fixtures and
    symbols. Test prose and negative-control literals such as a removed route
    path exist precisely to assert that the cinema surface is gone, and
    ``assert_no_live_legacy_paths`` checks separately that any test file naming
    a removed path also asserts its absence.
  * Also in test sources only, a line whose own wording is an absence
    assertion or terminology-guard machinery - ``def
    test_cinema_era_files_are_deleted``, ``test_no_supported_response_exposes_
    movie_ids``, ``REMOVED_FILES``, ``CINEMA_TERMS = re.compile(...)`` - is a
    negative control, not a surviving cinema name. Naming the removed thing is
    how such a test states what must not exist, so the term there is evidence
    the rebrand landed rather than evidence it stalled. The exemption is
    line-scoped and marker-driven (``no``, ``not``, ``never``, ``gone``,
    ``deleted``, ``removed``, ``legacy``, ``era``, ``404``, ``term``,
    ``pattern``, ``guard``, ...): an identifier that merely mentions a
    prohibited term without asserting its absence is still a failure, and R40
    (no movie-domain fixtures or watchlist semantics in test sources) keeps
    applying to every other line.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

DEMO_APP = Path(__file__).parents[1]
TEMPLATES_DIR = DEMO_APP / "templates"
STATIC_DIR = DEMO_APP / "static"
PY_TESTS_DIR = DEMO_APP / "tests"
JS_TESTS_DIR = STATIC_DIR / "tests"

#: TYPE_TERMS - the frozen prohibited sequence. Never shortened to make the
#: guard pass; precision is bought with word boundaries, not with omissions.
PROHIBITED_TERMS: tuple[str, ...] = (
    "Pocket Cinema",
    "PC",
    "movie",
    "film",
    "cinema",
    "watchlist",
    "poster",
    "runtime",
    "rating",
    "genre",
)

TYPE_TERMS = PROHIBITED_TERMS

#: Terms whose plural is equally prohibited on the supported surface.
_PLURALISABLE = frozenset(
    {"movie", "film", "cinema", "watchlist", "poster", "runtime", "rating", "genre"}
)

#: Removed cinema paths and pre-existing internal identifiers a test may name
#: while asserting that they are gone.
LEGACY_PATHS: tuple[str, ...] = (
    "/movie/",
    "/api/movies",
    "/api/watchlist",
    "#watchlist",
)

#: Evidence that a test file naming a removed path is asserting its absence.
ABSENCE_MARKERS: tuple[str, ...] = (
    "404",
    "not in",
    "gone",
    "deleted",
    "removed",
    "absent",
    "no longer",
    "must not",
)

#: Words that make a test-source line an absence assertion (a negative
#: control). Compared token-wise so 'era' does not fire inside 'operating'.
_ABSENCE_WORDS = frozenset(
    {
        "404",
        "absent",
        "dead",
        "delete",
        "deleted",
        "deletion",
        "era",
        "gone",
        "legacy",
        "never",
        "no",
        "not",
        "obsolete",
        "banned",
        "forbidden",
        "guard",
        "pattern",
        "prohibited",
        "term",
        "terms",
        "remove",
        "removed",
        "removal",
    }
)

#: Phrases that do the same across two tokens.
_ABSENCE_PHRASES = ("no longer", "not in", "must not", "does not")

_EXCERPT_RADIUS = 60


# --------------------------------------------------------------------------- #
# FN_TERM_PATTERN
# --------------------------------------------------------------------------- #


def _term_alternative(term: str) -> str:
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    if term.casefold() in _PLURALISABLE:
        return escaped + "s?"
    return escaped


def prohibited_pattern() -> re.Pattern[str]:
    """The one case-insensitive, word-boundary pattern for every term.

    The boundaries are stricter than ``\b`` on purpose. A term is a match when
    it is not glued to a preceding letter or digit and not continued by a
    lower-case letter or digit, which keeps innocent host words such as
    'upcoming', 'operating' and 'posterior' clean while still catching a public
    JSON key like 'movie_ids' or a symbol like 'watchlistToggle', where a plain
    word boundary would look through the separator and miss the term.
    """
    alternatives = "|".join(_term_alternative(term) for term in PROHIBITED_TERMS)
    return re.compile(
        rf"(?<![A-Za-z0-9])(?:{alternatives})(?![a-z0-9])", re.IGNORECASE
    )


PROHIBITED_PATTERN: re.Pattern[str] = prohibited_pattern()


# --------------------------------------------------------------------------- #
# FN_TERM_SCAN
# --------------------------------------------------------------------------- #


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - _EXCERPT_RADIUS)
    right = min(len(text), end + _EXCERPT_RADIUS)
    excerpt = text[left:right].replace("\n", " ")
    return re.sub(r"\s+", " ", excerpt).strip()


def assert_terms_absent(text: str, surface: str) -> None:
    """Raise AssertionError naming the term, the surface and the excerpt."""
    match = PROHIBITED_PATTERN.search(text)
    if match is None:
        return
    raise AssertionError(
        f"prohibited term {match.group(0)!r} found on surface {surface}\n"
        f"  excerpt: ...{_excerpt(text, match.start(), match.end())}...\n"
        "  Fix the surface. Tuning the guard by dropping a term or narrowing the "
        "surface list is not permitted."
    )


def assert_no_live_legacy_paths(path: Path, source: str) -> None:
    """A test naming a removed cinema path must also assert it is gone."""
    named = [legacy for legacy in LEGACY_PATHS if legacy in source]
    if not named:
        return
    lowered = source.casefold()
    if any(marker in lowered for marker in ABSENCE_MARKERS):
        return
    raise AssertionError(
        f"{path.name} names the removed path(s) {named!r} without asserting their "
        "absence, so a test could still depend on the cinema surface"
    )


# --------------------------------------------------------------------------- #
# Source reduction: comments never reach the customer, so they are not scanned
# --------------------------------------------------------------------------- #


def _strip_markup_comments(source: str) -> str:
    source = re.sub(r"\{#.*?#\}", " ", source, flags=re.DOTALL)
    source = re.sub(r"<!--.*?-->", " ", source, flags=re.DOTALL)
    return re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)


def _strip_python(source: str, drop_string_literals: bool = False) -> str:
    out: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char == "#":
            while index < length and source[index] != "\n":
                index += 1
            continue
        if char in "\"'":
            triple = source[index : index + 3]
            closer = triple if triple in ('"""', "'''") else char
            end = source.find(closer, index + len(closer))
            end = length if end == -1 else end + len(closer)
            literal = source[index:end]
            if not drop_string_literals and closer not in ('"""', "'''"):
                out.append(literal)
            else:
                out.append(" ")
            index = end
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _strip_js(source: str, drop_string_literals: bool = False) -> str:
    out: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        pair = source[index : index + 2]
        if pair == "//":
            while index < length and source[index] != "\n":
                index += 1
            continue
        if pair == "/*":
            end = source.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue
        char = source[index]
        if char in "\"'`":
            end = index + 1
            while end < length:
                if source[end] == "\\":
                    end += 2
                    continue
                if source[end] == char:
                    end += 1
                    break
                end += 1
            out.append(" " if drop_string_literals else source[index:end])
            index = end
            continue
        out.append(char)
        index += 1
    return "".join(out)


def scannable_source(path: Path, drop_string_literals: bool = False) -> str:
    """The part of a source file the guard scans, comments removed."""
    source = path.read_text(encoding="utf-8")
    suffix = path.suffix
    if suffix == ".py":
        return _strip_python(source, drop_string_literals)
    if suffix in {".js", ".mjs"}:
        return _strip_js(source, drop_string_literals)
    return _strip_markup_comments(source)


def _is_absence_assertion(line: str) -> bool:
    """True when the line's own wording states that something must not exist."""
    lowered = line.casefold()
    if any(phrase in lowered for phrase in _ABSENCE_PHRASES):
        return True
    return any(token in _ABSENCE_WORDS for token in re.split(r"[^a-z0-9]+", lowered))


def suite_identifier_surface(path: Path) -> str:
    """A test file's identifier text with its negative-control lines removed.

    Comments, docstrings and string literals are already gone; what is left is
    the identifier surface. A line that names a removed thing while asserting
    its absence is the negative control itself, so it is dropped rather than
    reported - see the documented exclusions in this module's docstring.
    """
    identifiers = scannable_source(path, drop_string_literals=True)
    return "\n".join(
        line for line in identifiers.splitlines() if not _is_absence_assertion(line)
    )


def _sorted_files(directory: Path, patterns: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(sorted(directory.glob(pattern)))
    return found


def template_sources() -> list[Path]:
    return _sorted_files(TEMPLATES_DIR, ("*.html", "_partials/*.html"))


def static_sources() -> list[Path]:
    return _sorted_files(STATIC_DIR, ("*.js", "*.css"))


def suite_sources() -> list[Path]:
    return _sorted_files(PY_TESTS_DIR, ("*.py",)) + _sorted_files(
        JS_TESTS_DIR, ("*.test.js",)
    )


def client_fetch_targets() -> list[tuple[str, str]]:
    """Every quoted path literal the browse and TV scripts name."""
    targets: list[tuple[str, str]] = []
    for path in _sorted_files(STATIC_DIR, ("*.js",)):
        source = path.read_text(encoding="utf-8")
        found = re.findall(r"""["'`](/[^"'`\s]*)["'`]""", source)
        if found:
            targets.append((f"client fetch targets in static/{path.name}", " ".join(found)))
    return targets


# --------------------------------------------------------------------------- #
# FN_TERM_SURFACES
# --------------------------------------------------------------------------- #


def _request(client: Any, method: str, label: str, path: str, expected: int, **kwargs: Any) -> str:
    response = getattr(client, method)(path, **kwargs)
    status = response.status_code
    if status != expected:
        raise AssertionError(
            f"surface {label} answered HTTP {status}, expected {expected}; an "
            "unreachable supported surface must never be silently skipped"
        )
    return response.get_data(as_text=True)


def first_recipe_id(client: Any) -> str:
    body = _request(client, "get", "GET /api/recipes", "/api/recipes", 200)
    recipes = json.loads(body)
    if not recipes:
        raise AssertionError("GET /api/recipes served an empty collection")
    return str(recipes[0]["id"])


def collect_surfaces(client: Any) -> list[tuple[str, str]]:
    """Every surface the guard scans, as (surface label, text) pairs."""
    recipe_id = first_recipe_id(client)
    surfaces: list[tuple[str, str]] = []

    pages: Sequence[tuple[str, str]] = (
        ("GET / (mobile browse page)", "/"),
        ("GET /?mode=tv (TV browse rails)", "/?mode=tv"),
        (f"GET /recipe/{recipe_id} (mobile recipe detail)", f"/recipe/{recipe_id}"),
        (
            f"GET /recipe/{recipe_id}?mode=tv (TV recipe detail)",
            f"/recipe/{recipe_id}?mode=tv",
        ),
    )
    endpoints: Sequence[tuple[str, str]] = (
        ("GET /api/recipes", "/api/recipes"),
        ("GET /api/recipes?q=oat", "/api/recipes?q=oat"),
        (f"GET /api/recipes/{recipe_id}", f"/api/recipes/{recipe_id}"),
        ("GET /api/cookbook", "/api/cookbook"),
        ("GET /api/rails", "/api/rails"),
    )
    for label, path in tuple(pages) + tuple(endpoints):
        surfaces.append((label, _request(client, "get", label, path, 200)))

    surfaces.append(
        (
            "GET /api/recipes/unknown-recipe (404 error body)",
            _request(
                client,
                "get",
                "GET /api/recipes/unknown-recipe",
                "/api/recipes/unknown-recipe",
                404,
            ),
        )
    )
    surfaces.append(
        (
            "POST /api/cookbook",
            _request(
                client,
                "post",
                "POST /api/cookbook",
                "/api/cookbook",
                201,
                json={"id": recipe_id},
            ),
        )
    )
    surfaces.append(
        (
            "POST /api/cookbook (unknown recipe error body)",
            _request(
                client,
                "post",
                "POST /api/cookbook (unknown recipe)",
                "/api/cookbook",
                400,
                json={"id": "not-a-recipe"},
            ),
        )
    )
    surfaces.append(
        (
            f"DELETE /api/cookbook/{recipe_id}",
            _request(
                client,
                "delete",
                f"DELETE /api/cookbook/{recipe_id}",
                f"/api/cookbook/{recipe_id}",
                200,
            ),
        )
    )

    for path in template_sources():
        surfaces.append((f"template source templates/{path.name}", scannable_source(path)))
    for path in static_sources():
        surfaces.append((f"static source static/{path.name}", scannable_source(path)))
    surfaces.extend(client_fetch_targets())
    for path in suite_sources():
        surfaces.append(
            (
                f"test source identifiers in {path.name}",
                suite_identifier_surface(path),
            )
        )
    return surfaces
