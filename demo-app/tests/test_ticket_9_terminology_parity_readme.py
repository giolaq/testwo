"""Acceptance tests for ticket #9: the terminology guard, the search parity
test and the TableStory application README.

Scope is the closing verification slice (MOD_TERMS, MOD_README, C_TERM_GUARD,
C_SEARCH_PY, C_SEARCH_JS, C_API_RECIPES, FLOW_GATES):

  * demo-app/tests/prohibited_terms.py defining the frozen term sequence once,
    compiling it into one case-insensitive word-boundary pattern, reporting a
    match with the term, the surface and the surrounding excerpt, and collecting
    the surfaces to scan through the Flask test client
  * the surface collection covering both modes of both pages, all six supported
    endpoints, and the template, static and test sources, and refusing to skip a
    surface that answers an unexpected status
  * demo-app/tests/test_terminology.py running that guard inside the existing
    pytest gate, never skipped and never xfailed, and never inspecting Git
    history or the PRD
  * demo-app/tests/test_parity.py exposing one shared sample-query list (mixed
    case, whitespace padded, one query per searchable field, one non-matching
    query) over which GET /api/recipes?q=... agrees with the shared
    normalisation and containment rule
  * demo-app/README.md letting a reviewer install, run, open both modes, walk
    the supported API, find the per-ticket pytest module map and perform the
    manual checks no headless gate can prove

The public seams used here are the create_app(testing=True) test client from
conftest.py, the server search helpers, and the modules this ticket adds. The
term sequence, the pattern, the scan and the surface collector are located by
their documented names with a duck-typed fallback, so a reasonable naming choice
is not turned into a failure.

Deliberately NOT asserted here: a zero-match scan of template, static or test
sources performed by this file. Those sources are surfaces of the shipped guard
(and its own pass is the gate's business); asserting them again here would
freeze source text owned by earlier slices. TV legibility, measured contrast,
focus scrolled into view and the 375px check stay manual reviewer steps, so this
file only asserts that the README records them. Nothing here asserts that a
later slice's routes, scripts or capabilities must remain absent.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

DEMO_APP = Path(__file__).parents[1]
TESTS_DIR = DEMO_APP / "tests"

if str(DEMO_APP) not in sys.path:
    sys.path.insert(0, str(DEMO_APP))

TERMS_MODULE = TESTS_DIR / "prohibited_terms.py"
GUARD_MODULE = TESTS_DIR / "test_terminology.py"
PARITY_MODULE = TESTS_DIR / "test_parity.py"
README = DEMO_APP / "README.md"

# The frozen sequence the ticket fixes, mirrored here so the guard cannot quietly
# drop a term. Order is the ticket's order; membership is what is asserted.
EXPECTED_TERMS = (
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

# Innocent words that merely contain a prohibited term as a substring. A
# word-boundary pattern must leave every one of them alone, because a guard that
# fires on these blocks honest work instead of catching a partial rebrand.
INNOCENT_HOST_WORDS = (
    "upcoming",  # contains 'pc'
    "operating",  # contains 'rating'
    "posterior",  # contains 'poster'
    "generating",  # contains 'rating'
)

SEARCHABLE_FIELDS = ("title", "description", "category", "dietary_tags", "ingredients")

SUPPORTED_ENDPOINTS = (
    "/api/recipes",
    "/api/recipes/<recipe_id>",
    "/api/cookbook",
    "/api/cookbook/<recipe_id>",
    "/api/rails",
)

PER_TICKET_TEST_MODULES = (
    "test_recipe_data.py",
    "test_cookbook_rails.py",
    "test_app.py",
    "test_recipe_page.py",
    "test_view_mode.py",
    "test_tv_detail.py",
    "test_parity.py",
    "test_terminology.py",
)


# --------------------------------------------------------------------------- #
# Loading the modules this ticket adds
# --------------------------------------------------------------------------- #


def _load_module(path: Path, description: str) -> ModuleType:
    """Import a module this ticket adds, failing as a behaviour assertion."""
    assert path.exists(), f"ticket #9 must add {path} ({description})"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None, f"{path} is not importable"
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def _terms() -> ModuleType:
    """The shared term definitions, loaded inside each test so a missing module
    fails as a behaviour assertion rather than as a fixture error."""
    return _load_module(TERMS_MODULE, "the shared prohibited-term definitions")


def _public_values(module: ModuleType) -> list:
    return [getattr(module, name) for name in dir(module) if not name.startswith("_")]


def _term_sequence(module: ModuleType):
    """The frozen term sequence, by documented name or by duck typing."""
    candidates = []
    for value in _public_values(module):
        if isinstance(value, (tuple, list, set, frozenset)) and value:
            members = list(value)
            if all(isinstance(item, str) for item in members):
                candidates.append(value)
    folded_expected = {term.casefold() for term in EXPECTED_TERMS}
    for value in candidates:
        if folded_expected <= {item.casefold() for item in value}:
            return value
    pytest.fail(
        f"{TERMS_MODULE} must define the frozen term sequence once (TYPE_TERMS / "
        f"PROHIBITED_TERMS) containing every term: {', '.join(EXPECTED_TERMS)}. "
        f"Found string collections: {candidates!r}"
    )


def _pattern(module: ModuleType) -> re.Pattern:
    """The single compiled pattern, from the factory function or the constant."""
    factory = getattr(module, "prohibited_pattern", None)
    if callable(factory):
        compiled = factory()
        assert isinstance(compiled, re.Pattern), (
            "prohibited_pattern() must return one compiled regular expression "
            f"pattern, got {type(compiled)!r}"
        )
        return compiled
    for value in _public_values(module):
        if isinstance(value, re.Pattern):
            return value
    pytest.fail(
        f"{TERMS_MODULE} must compile the term sequence into one pattern "
        "(FN_TERM_PATTERN, documented as prohibited_pattern())"
    )


def _scan(module: ModuleType):
    """The scan helper that raises AssertionError naming term, surface, excerpt."""
    scan = getattr(module, "assert_terms_absent", None)
    if callable(scan):
        return scan
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if callable(value) and "assert" in name and "term" in name:
            return value
    pytest.fail(
        f"{TERMS_MODULE} must expose the scan helper (FN_TERM_SCAN, documented as "
        "assert_terms_absent(text, surface))"
    )


def _collect_surfaces(module: ModuleType):
    collector = getattr(module, "collect_surfaces", None)
    if callable(collector):
        return collector
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if callable(value) and "surface" in name:
            return value
    pytest.fail(
        f"{TERMS_MODULE} must expose the surface collector (FN_TERM_SURFACES, "
        "documented as collect_surfaces(client))"
    )


def _surface_texts(surfaces) -> list[str]:
    """Flatten collected surfaces into text blobs, whatever the pair order is."""
    texts: list[str] = []
    for surface in surfaces:
        if isinstance(surface, (tuple, list)):
            texts.append(" ".join(str(part) for part in surface))
        else:
            texts.append(str(surface))
    return texts


# --------------------------------------------------------------------------- #
# The shared term definitions and the pattern
# --------------------------------------------------------------------------- #


def test_term_sequence_is_defined_once_and_frozen():
    sequence = _term_sequence(_terms())
    folded = {item.casefold() for item in sequence}

    for term in EXPECTED_TERMS:
        assert term.casefold() in folded, (
            f"the term {term!r} must stay in the shared sequence; the ticket "
            "forbids tuning the guard by dropping a term"
        )

    assert isinstance(sequence, (tuple, frozenset)), (
        "the term sequence must be frozen (a tuple or frozenset) so no test can "
        f"mutate the shared definition, got {type(sequence)!r}"
    )

    source = TERMS_MODULE.read_text(encoding="utf-8")
    lowered = source.casefold()
    for phrase in ("git", "internal", "identifier"):
        assert phrase in lowered, (
            f"{TERMS_MODULE} must document the exclusions (Git history, the PRD, "
            f"internal non-public filenames, pre-existing internal identifiers); "
            f"{phrase!r} is not mentioned"
        )


def test_pattern_matches_every_term_case_insensitively():
    pattern = _pattern(_terms())

    assert pattern.flags & re.IGNORECASE, "the pattern must be case-insensitive"

    for term in _term_sequence(_terms()):
        for variant in (term, term.upper(), term.casefold(), term.title()):
            probe = f"Recipe method steps mention {variant} in passing."
            assert pattern.search(probe), (
                f"the pattern must match {variant!r} on the supported surface"
            )


def test_pattern_is_word_boundary_aware():
    pattern = _pattern(_terms())

    for word in INNOCENT_HOST_WORDS:
        probe = f"The {word} recipe step is fine."
        found = pattern.search(probe)
        assert found is None, (
            f"the pattern must not fire on the innocent word {word!r}; it matched "
            f"{found.group(0)!r}. Tune for precision with word boundaries, never "
            "by dropping a term or narrowing the surface list"
        )

    clean = (
        "TableStory — Good food, clearly told. Save this recipe to My Cookbook. "
        "Popular this week. Ready in 30 minutes. Vegetarian favourites."
    )
    assert pattern.search(clean) is None, (
        "recipe-domain copy must not match the pattern"
    )


# --------------------------------------------------------------------------- #
# FN_TERM_SCAN: the failure report is the reviewer's evidence
# --------------------------------------------------------------------------- #


def test_scan_accepts_clean_recipe_domain_text():
    scan = _scan(_terms())
    scan(
        "<h1>TableStory</h1><p>Good food, clearly told.</p>",
        "GET / (mobile browse)",
    )


@pytest.mark.parametrize("term_index", [2, 5])
def test_scan_reports_the_term_surface_and_excerpt(term_index):
    """A reintroduced term must fail the guard with usable reviewer evidence."""
    scan = _scan(_terms())
    term = list(_term_sequence(_terms()))[term_index]
    surface = "GET /recipe/golden-oat-porridge (mobile detail)"
    excerpt_marker = "galette"
    text = (
        "<section class=\"recipe-detail\" data-recipe-id=\"spiced-plum-galette\">"
        "<h1>Spiced plum tart</h1><p>The " + excerpt_marker + " " + term
        + " label is back.</p></section>"
    )

    with pytest.raises(AssertionError) as raised:
        scan(text, surface)

    message = str(raised.value)
    assert term.casefold() in message.casefold(), (
        f"the failure must name the matched term {term!r}: {message!r}"
    )
    assert surface in message, (
        f"the failure must name the surface {surface!r}: {message!r}"
    )
    assert excerpt_marker in message, (
        "the failure must quote the surrounding excerpt so it is usable directly "
        f"as reviewer evidence: {message!r}"
    )


def test_scan_reports_a_public_json_key():
    """The guard must catch a term reintroduced as a public JSON field name."""
    scan = _scan(_terms())
    term = list(_term_sequence(_terms()))[2]

    # A bare key and a separator-delimited key: both keep the term a whole word,
    # so the documented word-boundary pattern is enough to catch them.
    for key in (term, f"{term}-ids"):
        payload = json.dumps({key: ["golden-oat-porridge"]})
        with pytest.raises(AssertionError) as raised:
            scan(payload, "GET /api/rails")
        assert term.casefold() in str(raised.value).casefold(), (
            f"the guard must report the term for the public JSON key {key!r}"
        )


# --------------------------------------------------------------------------- #
# FN_TERM_SURFACES: what the guard actually scans
# --------------------------------------------------------------------------- #


def test_surfaces_cover_both_modes_of_both_pages_and_the_sources(client):
    surfaces = list(_collect_surfaces(_terms())(client))
    assert len(surfaces) >= 10, (
        "the guard must scan both modes of both pages, all six supported "
        f"endpoints and the template, static and test sources; got {len(surfaces)} "
        "surfaces"
    )

    texts = _surface_texts(surfaces)
    blob = "\n".join(texts)

    expected_markers = {
        "the mobile browse page": "Good food, clearly told.",
        "the TV browse rails": "Popular this week",
        "a recipe detail page": "golden-oat-porridge",
        "GET /api/recipes": "prep_minutes",
        "GET /api/rails": "recipe_ids",
        "the template sources": "{%",
        "the client fetch targets": "/api/cookbook",
        "the test sources": "create_app(testing=True)",
    }
    for description, marker in expected_markers.items():
        assert marker in blob, (
            f"the collected surfaces must include {description} "
            f"(marker {marker!r} not found in any surface)"
        )

    tv_surfaces = [text for text in texts if "tv" in text.casefold()]
    assert len(tv_surfaces) >= 2, (
        "both the TV browse page and the TV recipe detail page must be scanned, "
        f"found {len(tv_surfaces)} surface(s) mentioning TV mode"
    )


class _BrokenStatusClient:
    """Test client proxy that makes one supported surface answer 500."""

    def __init__(self, client, broken_path: str) -> None:
        self._client = client
        self._broken_path = broken_path

    def __getattr__(self, name):
        attribute = getattr(self._client, name)
        if not callable(attribute):
            return attribute

        def call(path="/", *args, **kwargs):
            response = attribute(path, *args, **kwargs)
            if self._broken_path in str(path):
                response.status_code = 500
            return response

        return call


def test_surfaces_refuse_to_skip_a_broken_surface(client):
    """An unreachable supported surface must raise, never be silently skipped."""
    collector = _collect_surfaces(_terms())
    broken = _BrokenStatusClient(client, "/api/rails")

    with pytest.raises(Exception) as raised:
        collector(broken)

    assert not isinstance(raised.value, (AttributeError, TypeError)), (
        "the collector must reject the unexpected status rather than fail on the "
        f"client proxy: {raised.value!r}"
    )


# --------------------------------------------------------------------------- #
# FN_TEST_TERM_GUARD: the guard runs inside the existing pytest gate
# --------------------------------------------------------------------------- #


def test_guard_module_runs_the_scan_and_is_never_skipped(client):
    module = _load_module(GUARD_MODULE, "the terminology guard test")
    source = GUARD_MODULE.read_text(encoding="utf-8")

    for forbidden in ("pytest.mark.skip", "pytest.mark.xfail", "pytest.skip(", "pytest.xfail("):
        assert forbidden not in source, (
            f"{GUARD_MODULE} must never skip or xfail the guard; found {forbidden!r}"
        )

    guard_names = [name for name in dir(module) if name.startswith("test_")]
    assert guard_names, (
        f"{GUARD_MODULE} must define the guard as a collected pytest test "
        "(FN_TEST_TERM_GUARD)"
    )

    ran = False
    for name in guard_names:
        guard = getattr(module, name)
        if not callable(guard):
            continue
        try:
            guard(client)
        except TypeError:
            continue
        ran = True
    assert ran, (
        f"{GUARD_MODULE} must expose a guard test that takes the client fixture "
        f"and asserts zero matches; none of {guard_names} accepted a client"
    )


def test_guard_never_inspects_git_history():
    for path in (TERMS_MODULE, GUARD_MODULE):
        assert path.exists(), f"ticket #9 must add {path}"
        source = path.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        assert "subprocess" not in code, (
            f"{path} must not shell out; Git history is an excluded surface"
        )
        assert '".git' not in code and "'.git" not in code, (
            f"{path} must not read the Git directory; Git history is excluded"
        )


def test_supported_surface_is_free_of_the_terms(client):
    """Independent scan of the customer-visible and public surface."""
    pattern = _pattern(_terms())
    recipe_id = json.loads(client.get("/api/recipes").get_data(as_text=True))[0]["id"]

    surfaces = [
        ("GET / (mobile browse)", "/"),
        ("GET /?mode=tv (TV browse)", "/?mode=tv"),
        (f"GET /recipe/{recipe_id} (mobile detail)", f"/recipe/{recipe_id}"),
        (f"GET /recipe/{recipe_id}?mode=tv (TV detail)", f"/recipe/{recipe_id}?mode=tv"),
        ("GET /api/recipes", "/api/recipes"),
        (f"GET /api/recipes/{recipe_id}", f"/api/recipes/{recipe_id}"),
        ("GET /api/cookbook", "/api/cookbook"),
        ("GET /api/rails", "/api/rails"),
    ]
    for surface, path in surfaces:
        response = client.get(path)
        assert response.status_code == 200, f"{surface} answered {response.status_code}"
        found = pattern.search(response.get_data(as_text=True))
        assert found is None, f"{surface} still renders {found.group(0)!r}"

    saved = client.post("/api/cookbook", json={"id": recipe_id})
    assert saved.status_code == 201
    removed = client.delete(f"/api/cookbook/{recipe_id}")
    assert removed.status_code == 200
    for surface, response in (
        ("POST /api/cookbook", saved),
        (f"DELETE /api/cookbook/{recipe_id}", removed),
    ):
        found = pattern.search(response.get_data(as_text=True))
        assert found is None, f"{surface} still returns {found.group(0)!r}"

    for script in ("browse.js", "tv-browse.js", "tv-detail.js"):
        source = (DEMO_APP / "static" / script).read_text(encoding="utf-8")
        for target in re.findall(r"""["'`](/[^"'`\s]*)["'`]""", source):
            found = pattern.search(target)
            assert found is None, (
                f"static/{script} fetches {target!r}, which still uses {found.group(0)!r}"
            )


# --------------------------------------------------------------------------- #
# FN_TEST_PARITY: server and client search cannot drift
# --------------------------------------------------------------------------- #


def _shared_queries() -> list[str]:
    module = _load_module(PARITY_MODULE, "the server/client search parity test")
    candidates = [
        list(value)
        for value in _public_values(module)
        if isinstance(value, (tuple, list))
        and len(value) >= 6
        and all(isinstance(item, str) for item in value)
    ]
    assert candidates, (
        f"{PARITY_MODULE} must expose one shared sample-query list (mixed case, "
        "whitespace padded, one query per searchable field, one non-matching "
        "query) so the node suite can assert the same list"
    )
    return max(candidates, key=len)


def _load_collection():
    from recipe_data import load_recipes

    return load_recipes()


def _field_text(recipe: dict, field: str) -> str:
    value = recipe[field]
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value).casefold()
    return str(value).casefold()


def test_shared_query_list_covers_the_documented_cases():
    queries = _shared_queries()

    assert any(query != query.lower() and query != query.upper() for query in queries), (
        "the shared list must include a mixed-case query"
    )
    assert any(query != query.strip() for query in queries), (
        "the shared list must include a whitespace-padded query"
    )

    collection = _load_collection()
    recipes = list(collection.recipes)

    from recipe_search import filter_recipes

    assert any(not filter_recipes(recipes, query) for query in queries), (
        "the shared list must include one non-matching query"
    )

    for field in SEARCHABLE_FIELDS:
        covered = False
        for query in queries:
            normalised = query.strip().casefold()
            if not normalised:
                continue
            for recipe in recipes:
                others = " ".join(
                    _field_text(recipe, other)
                    for other in SEARCHABLE_FIELDS
                    if other != field
                )
                if normalised in _field_text(recipe, field) and normalised not in others:
                    covered = True
                    break
            if covered:
                break
        assert covered, (
            f"the shared list must include one query that matches through the "
            f"{field!r} field alone; queries were {queries!r}"
        )


def test_api_ids_equal_the_shared_rule_for_every_shared_query(client):
    from recipe_search import filter_recipes

    recipes = list(_load_collection().recipes)

    for query in _shared_queries():
        response = client.get("/api/recipes", query_string={"q": query})
        assert response.status_code == 200, (
            f"GET /api/recipes?q={query!r} answered {response.status_code}"
        )
        served = [recipe["id"] for recipe in json.loads(response.get_data(as_text=True))]
        expected = [recipe["id"] for recipe in filter_recipes(recipes, query)]
        assert served == expected, (
            f"for q={query!r} the endpoint returned {served!r} but the shared "
            f"normalisation and containment rule leaves {expected!r} visible"
        )


def test_parity_test_uses_the_public_endpoint():
    assert PARITY_MODULE.exists(), f"ticket #9 must add {PARITY_MODULE}"
    source = PARITY_MODULE.read_text(encoding="utf-8")
    assert "/api/recipes" in source, (
        f"{PARITY_MODULE} must compare the ids GET /api/recipes?q=... returns "
        "against the shared rule"
    )


# --------------------------------------------------------------------------- #
# MOD_README: the reviewer walkthrough
# --------------------------------------------------------------------------- #


def _readme() -> str:
    assert README.exists(), (
        "ticket #9 must add demo-app/README.md so a reviewer can install, run and "
        "open both modes from a clean checkout"
    )
    return README.read_text(encoding="utf-8")


def test_readme_documents_install_run_and_both_modes():
    text = _readme()
    lowered = text.casefold()

    assert "tablestory" in lowered, "the README must identify the product as TableStory"
    assert "requirements.txt" in text and "pip install" in lowered, (
        "the README must document installing dependencies with the project command"
    )
    assert "flask" in lowered, "the README must document starting the Flask server"
    assert "?mode=tv" in text, "the README must document opening TV mode via ?mode=tv"
    assert "localhost" in lowered or "127.0.0.1" in text, (
        "the README must show the address at which mobile mode opens"
    )


def test_readme_documents_the_supported_api_walkthrough():
    text = _readme()
    collapsed = re.sub(r"\s+", " ", text)

    for endpoint in SUPPORTED_ENDPOINTS:
        stem = endpoint.split("<")[0]
        assert stem in text, f"the README must walk through {endpoint}"

    for status in ("200", "201", "400", "404"):
        assert status in text, (
            f"the README must state the expected status code {status} in the API "
            "walkthrough"
        )

    assert (
        '{"error": "Recipe not found"}' in collapsed
        or '{ "error": "Recipe not found" }' in collapsed
        or '{"error":"Recipe not found"}' in collapsed
    ), "the README must quote the exact 404 error body"


def test_readme_documents_the_gates_and_the_module_map():
    text = _readme()

    assert "pytest" in text and "demo-app/tests" in text, (
        "the README must document the pytest verification gate command"
    )
    assert "node --test" in text and "demo-app/static/tests" in text, (
        "the README must document the node --test verification gate command"
    )

    for module in PER_TICKET_TEST_MODULES:
        assert module in text, (
            "the README must record that pytest coverage is spread across the "
            f"per-ticket modules; {module} is missing from the map"
        )


def test_readme_records_the_manual_reviewer_checks():
    text = _readme()
    lowered = text.casefold()

    assert "1920x1080" in lowered or "1920×1080" in lowered, (
        "the README must record the manual TV check at 1920x1080"
    )
    assert "wcag" in lowered and "contrast" in lowered, (
        "the README must record the measured WCAG AA contrast check"
    )
    assert "focus" in lowered, (
        "the README must record the check that focus is scrolled fully into view"
    )
    assert "clip" in lowered, (
        "the README must record the check for no clipped TV controls"
    )
    assert "375" in text, (
        "the README must record the no-horizontal-overflow check at 375px"
    )
