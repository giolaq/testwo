"""MOD_TERMS: the prohibited-terminology vocabulary and the surfaces to scan.

The vocabulary (TYPE_TERMS) is declared exactly once here as
:data:`PROHIBITED_TERMS` and compiled exactly once by :func:`prohibited_pattern`
(FN_TERM_PATTERN), so tightening the guard is a single edit and no test can
quietly scan a different set of words. :func:`assert_terms_absent`
(FN_TERM_SCAN) reports the term, the surface and the surrounding excerpt so a
failure is usable directly as reviewer evidence, and
:func:`collect_surfaces` (FN_TERM_SURFACES) drives the Flask test client over
the whole supported surface.

Scanned surface (R1, R5, R45)
-----------------------------
* ``GET /`` and ``GET /recipe/<recipe_id>`` in both mobile and TV mode, which
  covers rendered HTML, accessible labels, empty states and page metadata;
* all six supported endpoints, which covers JSON bodies and public JSON keys,
  including the 404 body of an unknown recipe lookup;
* the template sources and the customer-visible static sources (stylesheet and
  ES modules);
* the client fetch targets extracted from those ES modules;
* both test roots' sources.

Documented exclusions
---------------------
* Git history and the PRD are never read.
* Internal, non-public filenames and pre-existing internal identifiers are out
  of scope per the human decision captured in R5.
* Prose inside source comments is not customer-visible output, a public JSON key
  or a source symbol, so comments in the template and static sources are removed
  before the pattern is applied. This is a precision tune of where the pattern
  is applied; no term is ever dropped and no surface is ever removed from the
  list above.
* Test sources are held to R40 instead of to a literal term scan: no test source
  may still *depend* on a cinema-era module, symbol or film fixture
  (:func:`assert_no_cinema_dependency`). A literal scan cannot apply there,
  because the required legacy-route assertions have to keep naming the removed
  ``/movie/*``, ``/api/movies*`` and ``/api/watchlist*`` paths in order to prove
  they are gone.

Matching is case-insensitive and boundary aware: a term only matches when it is
not adjacent to a letter or a digit, so ``movie_ids``, ``movie-card`` and
``#watchlist`` are reported while ``upcoming``, ``topcoat``, ``filmography``,
``cinematography``, ``moviegoer`` and ``posterior`` are not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Iterator

DEMO_APP = Path(__file__).parents[1]

# TYPE_TERMS: the frozen prohibited vocabulary, declared once for every guard.
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

# The surfaces the guard scans, in the order collect_surfaces() returns them.
SCANNED_SURFACES: tuple[str, ...] = (
    "GET / and GET /recipe/<recipe_id> in mobile mode",
    "GET / and GET /recipe/<recipe_id> in TV mode",
    "the six supported JSON endpoints, their payload keys and the 404 body",
    "the template sources",
    "the customer-visible static sources",
    "the client fetch targets",
    "the sources in both test roots",
)

# Everything the guard deliberately does not inspect or does not fail on.
DOCUMENTED_EXCLUSIONS: tuple[str, ...] = (
    "Git history",
    "the PRD",
    "internal non-public filenames",
    "pre-existing internal identifiers",
    "prose inside source comments",
    "legacy-route assertions in test sources, which are held to R40 instead",
)

# Label prefix marking a surface whose text is test-source code.
TEST_SOURCE_PREFIX = "test source "

# Cinema-era files that must stay deleted, so no test can pass because a film
# fixture or a movie-era module survived (R40, C_LEGACY_GONE).
CINEMA_ERA_FILES: tuple[Path, ...] = (
    DEMO_APP / "catalog.json",
    DEMO_APP / "static" / "app-logic.js",
    DEMO_APP / "static" / "app.js",
    DEMO_APP / "static" / "tests" / "app-logic.test.js",
    DEMO_APP / "templates" / "index.html",
    DEMO_APP / "templates" / "detail.html",
)

# Cinema-era modules and symbols no test source may still import or load.
CINEMA_ERA_DEPENDENCIES: tuple[str, ...] = (
    "matchesMovie",
    "nextWatchlist",
    "load_catalog",
    "catalog.json",
    "app-logic",
    "index.html",
    "detail.html",
)

# A term matches only when it is not glued to a letter or a digit. '_' and '-'
# therefore act as boundaries, which is what catches a public key such as
# movie_ids or a class hook such as movie-card.
_LEFT = r"(?<![0-9A-Za-z])"
_RIGHT = r"(?![0-9A-Za-z])"

_EXCERPT_RADIUS = 40

_COMMENT_PATTERNS = (
    re.compile(r"/\*.*?\*/", re.DOTALL),  # CSS and JavaScript block comments
    re.compile(r"^[ \t]*//.*$", re.MULTILINE),  # JavaScript line comments
    re.compile(r"\{#.*?#\}", re.DOTALL),  # Jinja comments
    re.compile(r"<!--.*?-->", re.DOTALL),  # HTML comments
)

_FETCH_TARGET = re.compile(r"""['"`](/api/[^'"`]*)['"`]""")

_PY_IMPORT = re.compile(r"^\s*(?:import|from)\s")
_JS_IMPORT = re.compile(r"^\s*import\s")


def prohibited_pattern() -> re.Pattern[str]:
    """FN_TERM_PATTERN: the whole vocabulary as one case-insensitive pattern."""
    alternatives = sorted(PROHIBITED_TERMS, key=len, reverse=True)
    body = "|".join(term.replace(" ", r"[\s_-]+") for term in alternatives)
    return re.compile(f"{_LEFT}(?:{body}){_RIGHT}", re.IGNORECASE)


def assert_terms_absent(text: str, surface: str) -> None:
    """FN_TERM_SCAN: raise naming the term, the surface and the excerpt.

    Reports rather than sanitises: the guard must fail loudly and must never
    weaken its own assertion.
    """
    match = prohibited_pattern().search(text or "")
    if match is None:
        return None
    start = max(0, match.start() - _EXCERPT_RADIUS)
    end = min(len(text), match.end() + _EXCERPT_RADIUS)
    excerpt = text[start:end].replace("\n", " ")
    raise AssertionError(
        f"prohibited term {match.group(0)!r} found on surface {surface} "
        f"at offset {match.start()}; excerpt: ...{excerpt}..."
    )


def assert_no_cinema_dependency(text: str, surface: str) -> None:
    """R40 rule for test sources: no surviving cinema-era import or module load.

    A negative assertion that names a removed path is required coverage; an
    import of a removed module or film fixture is a surviving dependency.
    """
    for line in (text or "").splitlines():
        if not (_PY_IMPORT.match(line) or _JS_IMPORT.match(line)):
            continue
        for dependency in CINEMA_ERA_DEPENDENCIES:
            if dependency in line:
                raise AssertionError(
                    f"test source {surface} still imports the cinema-era "
                    f"dependency {dependency!r}: {line.strip()!r}"
                )
    return None


def strip_comments(text: str) -> str:
    """Remove comment prose from a template or static source before scanning."""
    for pattern in _COMMENT_PATTERNS:
        text = pattern.sub(" ", text)
    return text


def first_recipe_id() -> str:
    """The first fixture recipe id, used to address the detail page and lookup."""
    from recipe_data import load_recipes

    return load_recipes().recipes[0]["id"]


def _require(response: Any, expected: int, surface: str) -> str:
    status = getattr(response, "status_code", None)
    if status != expected:
        raise AssertionError(
            f"supported surface {surface} answered {status}, expected {expected}; "
            "an unreachable surface must fail the guard, never be skipped"
        )
    return response.get_data(as_text=True)


def _page_surfaces(client: Any, recipe_id: str) -> Iterator[tuple[str, str]]:
    for path, mode in (
        ("/", "mobile"),
        ("/?mode=tv", "tv"),
        (f"/recipe/{recipe_id}", "mobile"),
        (f"/recipe/{recipe_id}?mode=tv", "tv"),
    ):
        surface = f"GET {path} ({mode})"
        yield surface, _require(client.get(path), 200, surface)


def _endpoint_surfaces(client: Any, recipe_id: str) -> Iterator[tuple[str, str]]:
    for path in (
        "/api/recipes",
        f"/api/recipes/{recipe_id}",
        "/api/cookbook",
        "/api/rails",
    ):
        surface = f"GET {path}"
        yield surface, _require(client.get(path), 200, surface)

    surface = "POST /api/cookbook"
    yield surface, _require(
        client.post("/api/cookbook", json={"id": recipe_id}), 201, surface
    )

    surface = f"DELETE /api/cookbook/{recipe_id}"
    yield surface, _require(client.delete(f"/api/cookbook/{recipe_id}"), 200, surface)

    surface = "GET /api/recipes/<unknown recipe id> (404 body)"
    yield surface, _require(client.get("/api/recipes/not-a-recipe"), 404, surface)


def _source_files() -> Iterator[tuple[str, Path]]:
    for path in sorted((DEMO_APP / "templates").rglob("*.html")):
        yield f"source {path.relative_to(DEMO_APP)}", path
    for path in sorted((DEMO_APP / "static").glob("*.js")):
        yield f"source {path.relative_to(DEMO_APP)}", path
    for path in sorted((DEMO_APP / "static").glob("*.css")):
        yield f"source {path.relative_to(DEMO_APP)}", path


def _source_surfaces() -> Iterator[tuple[str, str]]:
    for surface, path in _source_files():
        yield surface, strip_comments(path.read_text(encoding="utf-8"))


def _fetch_target_surfaces() -> Iterator[tuple[str, str]]:
    for path in sorted((DEMO_APP / "static").glob("*.js")):
        targets = _FETCH_TARGET.findall(path.read_text(encoding="utf-8"))
        if targets:
            surface = f"client fetch targets in {path.relative_to(DEMO_APP)}"
            yield surface, "\n".join(targets)


def _test_source_surfaces() -> Iterator[tuple[str, str]]:
    roots = (DEMO_APP / "tests", DEMO_APP / "static" / "tests")
    for root in roots:
        for pattern in ("*.py", "*.js"):
            for path in sorted(root.glob(pattern)):
                surface = f"{TEST_SOURCE_PREFIX}{path.relative_to(DEMO_APP)}"
                yield surface, path.read_text(encoding="utf-8")


def is_test_source_surface(surface: str) -> bool:
    """True when a surface label denotes test-source code (held to R40)."""
    return surface.startswith(TEST_SOURCE_PREFIX)


def collect_surfaces(client: Any) -> list[tuple[str, str]]:
    """FN_TERM_SURFACES: every (surface, text) pair the guard has to scan.

    Raises when a supported page or endpoint answers an unexpected status,
    because an unreachable surface must not be silently skipped. Git history and
    the PRD are never read.
    """
    recipe_id = first_recipe_id()
    surfaces: list[tuple[str, str]] = []
    surfaces.extend(_page_surfaces(client, recipe_id))
    surfaces.extend(_endpoint_surfaces(client, recipe_id))
    surfaces.extend(_source_surfaces())
    surfaces.extend(_fetch_target_surfaces())
    surfaces.extend(_test_source_surfaces())
    return surfaces


def json_keys(payload: Any, keys: set[str] | None = None) -> set[str]:
    """Every key name in a JSON payload, so public keys can be scanned alone."""
    found: set[str] = set() if keys is None else keys
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            json_keys(value, found)
    elif isinstance(payload, list):
        for item in payload:
            json_keys(item, found)
    return found


def iter_terms() -> Iterable[str]:
    """The vocabulary, for tests that report per-term coverage."""
    return PROHIBITED_TERMS
