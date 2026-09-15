"""Acceptance tests for ticket #9: terminology guard, search parity, README.

Three deliverables are asserted here, all through public seams and all offline:

* ``demo-app/tests/prohibited_terms.py`` (MOD_TERMS) must define the frozen
  ten-term vocabulary once (TYPE_TERMS), compile it into a single
  case-insensitive word-boundary pattern (FN_TERM_PATTERN), raise an
  ``AssertionError`` naming the term, the surface and the surrounding excerpt
  (FN_TERM_SCAN), and drive the Flask test client over both modes of both pages
  plus all six supported endpoints and the template, static and test sources
  (FN_TERM_SURFACES). The guard itself must report zero matches on the supported
  surface, and must raise rather than silently skip a surface that answers an
  unexpected status.
* server/client search parity (FN_TEST_PARITY): for one shared sample-query list
  the ids from ``GET /api/recipes?q=...`` equal the ids the shared normalisation
  and containment rule leaves visible. The identical list and the identical
  expected ids are asserted client-side in
  ``demo-app/static/tests/ticket-9-search-parity.test.js``, and this module pins
  that the Node suite still carries them, so the Python and JavaScript
  predicates cannot drift.
* ``demo-app/README.md`` (MOD_README) must let a reviewer install, run and open
  both modes from a clean checkout, and must document the six-endpoint
  walkthrough with its status codes and exact 404 body, the two verification
  gate commands, the per-ticket pytest module map, and the manual TV / contrast /
  375px checks that no headless gate can prove.

Terminology scope follows R5: the customer-visible surface, page metadata,
public JSON keys and client fetch targets are scanned; Git history, the PRD,
internal non-public filenames and pre-existing internal identifiers are not.
Test sources are held to R40 (no movie-domain module, symbol or film fixture is
still depended on) rather than to a literal term scan, because the required
legacy-route assertions must keep naming the removed cinema paths.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

from recipe_data import load_recipes
from recipe_search import filter_recipes, normalise_query, searchable_text

DEMO_APP = Path(__file__).parents[1]
TESTS_DIR = DEMO_APP / "tests"
GUARD_MODULE = TESTS_DIR / "prohibited_terms.py"
TERM_TEST = TESTS_DIR / "test_terminology.py"
PARITY_TEST = TESTS_DIR / "test_parity.py"
README = DEMO_APP / "README.md"
NODE_PARITY_TEST = DEMO_APP / "static" / "tests" / "ticket-9-search-parity.test.js"

# TYPE_TERMS: the frozen prohibited vocabulary, in the order the ticket fixes it.
TERMS = (
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

# The six supported endpoints plus both modes of both pages: the surface the
# guard has to cover. '{id}' is substituted with the first fixture recipe id.
SUPPORTED_PAGES = ("/", "/?mode=tv", "/recipe/{id}", "/recipe/{id}?mode=tv")
SUPPORTED_ENDPOINTS = (
    "/api/recipes",
    "/api/recipes/{id}",
    "/api/cookbook",
    "/api/rails",
)

# The shared sample-query list (mixed case, whitespace padded, one query per
# searchable field, one non-matching query, plus the empty query). The identical
# list and expected ids appear in ticket-9-search-parity.test.js.
PARITY_CASES = (
    ("weeknight", ["weeknight-salmon-traybake"]),
    ("warm start to the day", ["golden-oat-porridge"]),
    (
        "DESSERT",
        ["dark-chocolate-mousse", "honey-roast-plums", "no-bake-peanut-oat-bars"],
    ),
    (
        " vegan",
        [
            "sunrise-berry-smoothie-bowl",
            "lemon-chickpea-salad",
            "slow-simmered-lentil-stew",
            "spiced-butternut-curry",
            "no-bake-peanut-oat-bars",
        ],
    ),
    ("GARLIC", ["slow-simmered-lentil-stew"]),
    ("  Lemon Chickpea  ", ["lemon-chickpea-salad"]),
    ("pineapple pizza", []),
    (
        "",
        [
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
        ],
    ),
)

# The per-ticket pytest modules the README has to map for a reviewer.
PYTEST_MODULE_MAP = (
    "test_recipe_data.py",
    "test_cookbook_rails.py",
    "test_app.py",
    "test_recipe_page.py",
    "test_view_mode.py",
    "test_tv_detail.py",
    "test_parity.py",
    "test_terminology.py",
)

# Cinema-era client and data files that must stay deleted (R40, C_LEGACY_GONE):
# no test may pass because one of them survived.
CINEMA_ERA_FILES = (
    DEMO_APP / "catalog.json",
    DEMO_APP / "static" / "app-logic.js",
    DEMO_APP / "static" / "app.js",
    DEMO_APP / "static" / "tests" / "app-logic.test.js",
    DEMO_APP / "templates" / "index.html",
    DEMO_APP / "templates" / "detail.html",
)

# Cinema-era symbols and fixtures no test source may still depend on (R40).
CINEMA_ERA_SYMBOLS = ("matchesMovie", "nextWatchlist", "load_catalog", "catalog.json")


def _recipe_id() -> str:
    return load_recipes().recipes[0]["id"]


def _load_guard():
    """Import MOD_TERMS, failing as a behaviour assertion when it is missing."""
    assert GUARD_MODULE.exists(), (
        f"ticket #9 must add {GUARD_MODULE} defining the prohibited-term "
        "vocabulary once (TYPE_TERMS) plus the pattern, scan and surface helpers"
    )
    if str(TESTS_DIR) not in sys.path:
        sys.path.insert(0, str(TESTS_DIR))
    return importlib.import_module("prohibited_terms")


def _guard_attr(module, name: str, description: str):
    attribute = getattr(module, name, None)
    assert callable(attribute), (
        f"{GUARD_MODULE.name} must expose {name}() - {description}"
    )
    return attribute


def _term_sequence(module):
    """The single frozen term vocabulary declared by MOD_TERMS."""
    expected = {term.casefold() for term in TERMS}
    found = []
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if isinstance(value, (tuple, frozenset, list, set)) and value:
            if not all(isinstance(item, str) for item in value):
                continue
            if {item.casefold() for item in value} == expected:
                found.append((name, value))
    assert found, (
        f"{GUARD_MODULE.name} must define the ten prohibited terms once as a "
        f"module-level sequence (TYPE_TERMS): {list(TERMS)}"
    )
    assert len(found) == 1, (
        "the prohibited terms must be defined exactly once, not duplicated; "
        f"found {[name for name, _ in found]}"
    )
    name, value = found[0]
    assert isinstance(value, (tuple, frozenset)), (
        f"{GUARD_MODULE.name}.{name} must be a frozen sequence (tuple or "
        f"frozenset) so the vocabulary cannot be mutated; got {type(value).__name__}"
    )
    return value


def _json_keys(payload, keys: set[str]) -> set[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            _json_keys(value, keys)
    elif isinstance(payload, list):
        for item in payload:
            _json_keys(item, keys)
    return keys


class _BrokenResponse:
    """Stand-in for a supported surface answering an unexpected status."""

    status_code = 500
    mimetype = "text/html"
    headers: dict[str, str] = {}
    json = None
    text = ""
    data = b""

    def get_data(self, as_text: bool = False):
        return "" if as_text else b""

    def get_json(self, *args, **kwargs):
        return None


class _BrokenClient:
    """Delegates to the real test client but breaks one supported surface."""

    def __init__(self, client, broken_path: str) -> None:
        self._client = client
        self._broken = broken_path

    def _broken_request(self, path: str) -> bool:
        return str(path).split("?")[0] == self._broken

    def get(self, path, *args, **kwargs):
        if self._broken_request(path):
            return _BrokenResponse()
        return self._client.get(path, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._client, name)


# --------------------------------------------------------------------------
# Criterion 1 and 2: the terminology guard (C_TERM_GUARD, R1, R5, R45)
# --------------------------------------------------------------------------


def test_prohibited_terms_module_defines_the_frozen_vocabulary_once():
    module = _load_guard()
    terms = _term_sequence(module)
    assert {term.casefold() for term in terms} == {term.casefold() for term in TERMS}


def test_prohibited_pattern_is_case_insensitive_and_word_boundary_aware():
    module = _load_guard()
    pattern = _guard_attr(
        module,
        "prohibited_pattern",
        "FN_TERM_PATTERN, compiling the terms into one case-insensitive "
        "word-boundary pattern",
    )()
    assert isinstance(pattern, re.Pattern), (
        "prohibited_pattern() must return a single compiled pattern"
    )
    assert pattern.flags & re.IGNORECASE, "the pattern must be case-insensitive"

    for term in TERMS:
        for variant in (term, term.upper(), term.lower(), term.title()):
            haystack = f"a rendered sentence with {variant} inside it"
            assert pattern.search(haystack), (
                f"the pattern must match the prohibited term {variant!r}"
            )

    # Punctuation, markup and identifier separators still count: a class hook or
    # a public JSON key is customer-visible or public surface (R5, R28).
    for haystack in (
        'class="movie-card"',
        "<title>Pocket Cinema</title>",
        "#watchlist",
        '{"movie_ids": []}',
        '{"watchlist_ids": []}',
    ):
        assert pattern.search(haystack), f"the pattern must match {haystack!r}"

    # Precision: innocent words that merely contain a term as a substring must
    # not block work (tuning is by precision, never by dropping a term).
    for innocent in (
        "upcoming",
        "topcoat",
        "filmography",
        "cinematography",
        "moviegoer",
        "posterior",
        "a recipe collection",
    ):
        assert not pattern.search(innocent), (
            f"the pattern must not report the innocent substring in {innocent!r}"
        )


def test_term_scan_reports_the_term_the_surface_and_the_excerpt():
    module = _load_guard()
    scan = _guard_attr(
        module,
        "assert_terms_absent",
        "FN_TERM_SCAN, raising AssertionError naming the term, surface and excerpt",
    )

    assert scan("Good food, clearly told. 13 recipes", "GET / (mobile)") is None

    surface = "GET / (mobile)"
    with pytest.raises(AssertionError) as excinfo:
        scan("<p>zebrafish movie kumquat</p>", surface)
    message = str(excinfo.value)
    assert "movie" in message.casefold(), "the failure must name the matched term"
    assert surface in message, "the failure must name the surface"
    assert "zebrafish" in message or "kumquat" in message, (
        "the failure must include the surrounding excerpt so it is usable "
        f"directly as reviewer evidence; got {message!r}"
    )

    # A reintroduced public JSON key fails the same way.
    with pytest.raises(AssertionError) as excinfo:
        scan(json.dumps({"movie_ids": ["afterlight"]}), "GET /api/rails")
    key_message = str(excinfo.value)
    assert "movie" in key_message.casefold()
    assert "GET /api/rails" in key_message


def test_term_surfaces_cover_both_modes_both_pages_and_every_endpoint(client):
    module = _load_guard()
    collect = _guard_attr(
        module,
        "collect_surfaces",
        "FN_TERM_SURFACES, driving the test client over the supported surface",
    )
    surfaces = list(collect(client))
    assert surfaces, "collect_surfaces() must return the surfaces to scan"
    for entry in surfaces:
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"each surface must be a (surface, text) pair; got {entry!r}"
        )
        label, text = entry
        assert isinstance(label, str) and label, "each surface needs a name"
        assert isinstance(text, str), f"surface {label!r} must yield text to scan"

    labels = " | ".join(label for label, _ in surfaces)
    blob = "\n".join(text for _, text in surfaces)

    for path in SUPPORTED_PAGES + SUPPORTED_ENDPOINTS:
        needle = path.format(id=_recipe_id())
        assert needle in labels, (
            f"collect_surfaces() must scan {needle}; scanned surfaces were {labels}"
        )

    # The rendered content of each mode and each response type is really present.
    for marker, description in (
        ("Good food, clearly told.", "the mobile browse page render"),
        ("Popular this week", "the TV browse page render"),
        ("recipe_ids", "the GET /api/rails payload"),
        ("prep_minutes", "the GET /api/recipes payload"),
        ("data-search-text", "the template sources"),
        ("/api/cookbook", "the client fetch targets"),
        ("def test_", "the test sources"),
    ):
        assert marker in blob, (
            f"collect_surfaces() must include {description} (missing {marker!r})"
        )

    # Documented exclusions: never Git history, never the PRD.
    assert ".git/" not in labels and "/.git" not in labels, (
        "the guard must never inspect Git history"
    )
    assert "prd" not in labels.casefold(), "the guard must never inspect the PRD"


def test_term_surfaces_refuse_a_surface_with_an_unexpected_status(client):
    module = _load_guard()
    collect = _guard_attr(
        module,
        "collect_surfaces",
        "FN_TERM_SURFACES, which must raise rather than skip an unreachable surface",
    )
    broken = _BrokenClient(client, "/api/rails")
    with pytest.raises(Exception):
        collect(broken)


def test_supported_surface_has_zero_prohibited_terms(client):
    """The guard's own subject: rendered pages, JSON bodies and page metadata."""
    module = _load_guard()
    pattern = _guard_attr(module, "prohibited_pattern", "FN_TERM_PATTERN")()
    recipe_id = _recipe_id()

    for path in SUPPORTED_PAGES + SUPPORTED_ENDPOINTS:
        target = path.format(id=recipe_id)
        response = client.get(target)
        assert response.status_code == 200, (
            f"{target} must answer 200 so the guard cannot silently skip it"
        )
        body = response.get_data(as_text=True)
        match = pattern.search(body)
        found = match.group(0) if match else ""
        excerpt = body[max(0, match.start() - 40) : match.end() + 40] if match else ""
        assert match is None, (
            f"{target} still renders the prohibited term {found!r}: {excerpt!r}"
        )

    # Public JSON keys, including the mutation responses.
    saved = client.post("/api/cookbook", json={"id": recipe_id})
    assert saved.status_code == 201
    removed = client.delete(f"/api/cookbook/{recipe_id}")
    assert removed.status_code == 200
    for label, payload in (
        ("GET /api/recipes", client.get("/api/recipes").get_json()),
        ("GET /api/rails", client.get("/api/rails").get_json()),
        ("POST /api/cookbook", saved.get_json()),
        (f"DELETE /api/cookbook/{recipe_id}", removed.get_json()),
    ):
        for key in _json_keys(payload, set()):
            assert not pattern.search(key), (
                f"{label} exposes the prohibited public JSON key {key!r}"
            )

    # The removed 404 body is customer-visible output too.
    missing = client.get("/api/recipes/not-a-recipe")
    assert missing.status_code == 404
    assert missing.get_json() == {"error": "Recipe not found"}
    assert pattern.search(missing.get_data(as_text=True)) is None

    # Client fetch targets and the customer-visible stylesheet.
    for source in sorted((DEMO_APP / "static").glob("*.js")):
        text = source.read_text(encoding="utf-8")
        for target in re.findall(r"""['"`](/api/[^'"`]*)['"`]""", text):
            assert not pattern.search(target), (
                f"{source.name} fetches the cinema-era path {target!r}"
            )


def test_no_test_source_depends_on_a_cinema_era_module_or_fixture():
    """R40: no test passes because a movie endpoint or film fixture survived."""
    for path in CINEMA_ERA_FILES:
        assert not path.exists(), f"the cinema-era file {path} must stay deleted"

    sources = sorted(TESTS_DIR.glob("*.py")) + sorted(
        (DEMO_APP / "static" / "tests").glob("*.js")
    )
    assert sources, "both test roots must contain migrated suites"
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for symbol in CINEMA_ERA_SYMBOLS:
            for line in text.splitlines():
                if symbol not in line:
                    continue
                # A negative assertion naming a removed symbol is required
                # coverage; importing one is a surviving dependency.
                stripped = line.strip()
                assert not stripped.startswith(("import ", "from ")), (
                    f"{source.name} still imports the cinema-era symbol {symbol!r}: "
                    f"{stripped!r}"
                )


def test_terminology_and_parity_tests_are_present_and_never_skipped():
    for path, description in (
        (TERM_TEST, "FN_TEST_TERM_GUARD, asserting zero matches"),
        (PARITY_TEST, "FN_TEST_PARITY, asserting server/client search parity"),
    ):
        assert path.exists(), f"ticket #9 must add {path} implementing {description}"
        text = path.read_text(encoding="utf-8")
        for weakened in ("pytest.mark.skip", "pytest.skip", "xfail"):
            assert weakened not in text, (
                f"{path.name} must not {weakened} - the guard may never be weakened"
            )


# --------------------------------------------------------------------------
# Criterion 4: server/client search parity (C_SEARCH_PY, C_SEARCH_JS, R15, R18)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("query,expected_ids", PARITY_CASES)
def test_api_recipes_matches_the_shared_rule_for_every_sample_query(
    client, query, expected_ids
):
    collection = load_recipes()

    response = client.get("/api/recipes", query_string={"q": query})
    assert response.status_code == 200
    api_ids = [recipe["id"] for recipe in response.get_json()]

    # The shared normalisation and containment rule, applied independently.
    folded = normalise_query(query)
    rule_ids = [
        recipe["id"]
        for recipe in collection.recipes
        if not folded or folded in searchable_text(recipe)
    ]

    assert api_ids == expected_ids, (
        f"GET /api/recipes?q={query!r} returned {api_ids}, expected {expected_ids}"
    )
    assert api_ids == rule_ids, (
        f"GET /api/recipes?q={query!r} disagrees with the shared rule: "
        f"{api_ids} vs {rule_ids}"
    )
    assert api_ids == [
        recipe["id"] for recipe in filter_recipes(collection.recipes, query)
    ]


def test_browse_cards_expose_the_same_searchable_text_the_api_filters_on(client):
    """The client filters the text the server produced, so parity is structural."""
    collection = load_recipes()
    html = client.get("/").get_data(as_text=True)
    rendered = dict(
        re.findall(
            r'data-recipe-id="([^"]+)"\s+data-search-text="([^"]*)"',
            html,
        )
    )
    assert len(rendered) == len(collection.recipes), (
        "every recipe card must carry the server-rendered search text"
    )
    for recipe in collection.recipes:
        expected = searchable_text(recipe)
        actual = rendered[recipe["id"]].replace("&#34;", '"').replace("&amp;", "&")
        assert actual == expected, (
            f"card {recipe['id']} exposes search text that differs from "
            "searchable_text(), so the client would search other fields"
        )


def test_node_suite_asserts_the_same_shared_parity_queries():
    assert NODE_PARITY_TEST.exists(), (
        f"ticket #9 must keep {NODE_PARITY_TEST.name} asserting the shared query "
        "list against the client predicate"
    )
    text = NODE_PARITY_TEST.read_text(encoding="utf-8")
    for query, expected_ids in PARITY_CASES:
        if query:
            assert query in text, (
                f"the Node suite must assert the shared sample query {query!r}"
            )
        for recipe_id in expected_ids:
            assert recipe_id in text, (
                f"the Node suite must assert {recipe_id!r} for query {query!r}"
            )


# --------------------------------------------------------------------------
# Criterion 5: the reviewer README (MOD_README, R39, TEST_MANUAL_TV)
# --------------------------------------------------------------------------


def _readme_text() -> str:
    assert README.exists(), (
        f"ticket #9 must add {README} identifying the product as TableStory and "
        "documenting install, run, mobile mode, TV mode, the API walkthrough, "
        "the pytest module map and the manual reviewer checks"
    )
    return README.read_text(encoding="utf-8")


def test_readme_lets_a_reviewer_install_run_and_open_both_modes():
    text = _readme_text()
    lowered = text.casefold()

    assert "tablestory" in lowered, "the README must identify the product as TableStory"
    assert "pip install -r" in lowered and "requirements.txt" in lowered, (
        "the README must document the project install command"
    )
    assert re.search(r"(python\s+app\.py|flask\s+(--app|run))", lowered), (
        "the README must document how to start the Flask server"
    )
    assert re.search(r"(localhost|127\.0\.0\.1)[:/]?5000|:5000", lowered), (
        "the README must say which address opens mobile mode"
    )
    assert "?mode=tv" in lowered, "the README must document opening TV mode"


def test_readme_documents_the_supported_six_endpoint_walkthrough():
    text = _readme_text()

    for endpoint in (
        "GET /api/recipes",
        "GET /api/recipes/",
        "GET /api/cookbook",
        "POST /api/cookbook",
        "DELETE /api/cookbook/",
        "GET /api/rails",
    ):
        assert endpoint in text, f"the README must document {endpoint}"

    for status in ("200", "201", "400", "404"):
        assert status in text, f"the README must state the expected status {status}"

    assert '{"error": "Recipe not found"}' in text, (
        "the README must quote the exact 404 error body"
    )


def test_readme_documents_the_gates_the_module_map_and_the_manual_checks():
    text = _readme_text()
    lowered = text.casefold()

    assert "pytest -q demo-app/tests" in text, (
        "the README must document the api-tests gate command"
    )
    assert "node --test demo-app/static/tests/*.test.js" in text, (
        "the README must document the ui-logic-tests gate command"
    )

    for module in PYTEST_MODULE_MAP:
        assert module in text, (
            f"the README must map pytest coverage to {module} so a reviewer knows "
            "where each area is asserted"
        )

    for marker, description in (
        ("1920", "the TV viewport width for the legibility check"),
        ("1080", "the TV viewport height for the legibility check"),
        ("wcag", "the measured WCAG AA contrast check"),
        ("contrast", "the measured contrast check"),
        ("375", "the 375px mobile overflow check"),
        ("focus", "the focus-scrolled-into-view check"),
        ("clip", "the no-clipped-TV-controls check"),
        ("overflow", "the no-horizontal-overflow check"),
    ):
        assert marker in lowered, (
            f"the README must record the manual reviewer check for {description}"
        )


# --------------------------------------------------------------------------
# Criterion 6: no dependency was added (C_GATES, R42)
# --------------------------------------------------------------------------


def test_no_runtime_dependency_was_added():
    requirements = [
        line.strip()
        for line in (DEMO_APP / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert requirements == ["Flask>=3.1,<4", "pytest>=8,<9"], (
        f"requirements.txt must gain no dependency; got {requirements}"
    )

    package = json.loads((DEMO_APP / "package.json").read_text(encoding="utf-8"))
    assert package.get("type") == "module", (
        "package.json must keep type=module so node --test can import the logic modules"
    )
    for field in ("dependencies", "devDependencies", "peerDependencies"):
        assert not package.get(field), f"package.json must declare no {field}"
