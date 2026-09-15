"""Acceptance tests for ticket #3: recipe API, recipe routing and the atomic
removal of the cinema surface.

Scope is the ticket's own files:
  demo-app/app.py           (FN_CREATE_APP, MOD_APP)
  demo-app/api_routes.py    (MOD_API, the six supported endpoints)
  demo-app/page_routes.py   (MOD_PAGES, GET / and GET /recipe/<recipe_id>)
  demo-app/templates/       (browse.html, recipe.html, _partials/)
  the legacy deletions      (catalog.json, index.html, detail.html, app.js,
                             app-logic.js, app-logic.test.js)

Deliberately NOT asserted here, because the ticket defers them:
  * the full mobile detail presentation (metadata block, ingredient list,
    numbered steps, state-bearing save control markup) belongs to T-DETAIL;
    this file asserts only that FN_DETAIL_CONTEXT already supplies that data.
  * view-mode resolution, TV templates and TV rails markup belong to T-TVBROWSE.
  * the browse DOM binding belongs to T-MOBCLIENT, so the save control is
    exercised through the API rather than through a simulated click.

Everything runs through the public seams: the create_app(testing=True)
test_client fixture from conftest.py, and the pure context builders. Imports of
the ticket's new modules are lazy behind a file-existence assertion so a missing
module surfaces as a behaviour assertion failure rather than a collection error.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

DEMO_APP = Path(__file__).parents[1]

if str(DEMO_APP) not in sys.path:
    sys.path.insert(0, str(DEMO_APP))

TAGLINE = "Good food, clearly told."
EMPTY_STATE = "No recipes found. Try another ingredient or dish."
RECIPE_NOT_FOUND = {"error": "Recipe not found"}

RAIL_NAMES = (
    "Popular this week",
    "Ready in 30 minutes",
    "Vegetarian favourites",
    "My Cookbook",
)

UNKNOWN_ID = "no-such-recipe-id"

# The removed cinema surface. Every entry must answer 404 - never 2xx, never a
# redirect - with no alias, shim or flag registered anywhere in the app.
LEGACY_ROUTES = (
    ("GET", "/movie/afterlight"),
    ("GET", "/movie/golden-oat-porridge"),
    ("GET", "/api/movies"),
    ("GET", "/api/movies/afterlight"),
    ("GET", "/api/watchlist"),
    ("POST", "/api/watchlist"),
    ("GET", "/api/watchlist/afterlight"),
    ("DELETE", "/api/watchlist/afterlight"),
)

DELETED_PATHS = (
    "catalog.json",
    "templates/index.html",
    "templates/detail.html",
    "static/app.js",
    "static/app-logic.js",
    "static/tests/app-logic.test.js",
)

# Cinema-domain vocabulary that must not survive on the customer-visible or
# public surface (R5, scoped per the human decision on blocking question 2).
CINEMA_TERMS = re.compile(
    r"\b(pocket cinema|cinema|movies?|films?|watchlist|posters?|runtime|genres?)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# lazy module / attribute access
# --------------------------------------------------------------------------- #
def _module(name: str):
    source = DEMO_APP / f"{name}.py"
    assert source.is_file(), f"ticket #3 requires demo-app/{name}.py"
    module = sys.modules.get(name)
    if module is not None and getattr(module, "__file__", None) == str(source):
        return module
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _attr(module_name: str, *candidates: str):
    module = _module(module_name)
    for candidate in candidates:
        if hasattr(module, candidate):
            return getattr(module, candidate)
    raise AssertionError(
        f"demo-app/{module_name}.py must define {' or '.join(candidates)}"
    )


def _collection():
    return _attr("recipe_data", "load_recipes")()


def _recipes():
    return list(_collection().recipes)


def _searchable_text(recipe: dict) -> str:
    return _attr("recipe_search", "searchable_text")(recipe)


def _total_minutes(recipe: dict) -> int:
    return _attr("recipe_search", "total_minutes")(recipe)


def _store(collection=None):
    collection = _collection() if collection is None else collection
    return _attr("cookbook", "CookbookStore")(collection)


def _call_by_parameter_name(func, **available):
    """Call ``func`` supplying only the arguments its signature actually names.

    The ticket leaves one documented seam for T-TVBROWSE to inject view-mode
    resolution, so the context builders may or may not take a view-mode
    argument yet. Binding by parameter name keeps this test focused on the
    behaviour the ticket owns instead of on a signature detail a later slice
    is allowed to extend.
    """
    signature = inspect.signature(func)
    kwargs = {}
    for name, parameter in signature.parameters.items():
        if name in available:
            kwargs[name] = available[name]
        elif parameter.default is inspect.Parameter.empty:
            raise AssertionError(
                f"{func.__name__} requires an unexpected argument {name!r}; "
                "expected some of " + ", ".join(sorted(available))
            )
    return func(**kwargs)


def _flatten(context) -> dict:
    """Context values plus one level of nested mapping values, for lookup."""
    assert isinstance(context, dict), (
        f"expected a context mapping, got {type(context)!r}"
    )
    flat: dict = dict(context)
    for value in list(context.values()):
        if isinstance(value, dict):
            for key, nested in value.items():
                flat.setdefault(key, nested)
    return flat


def _values(context) -> list:
    flat = _flatten(context)
    out: list = list(flat.values())
    for value in list(flat.values()):
        if isinstance(value, (list, tuple)):
            out.extend(value)
    return out


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _json(response):
    assert response.mimetype == "application/json", (
        f"expected a JSON response, got {response.mimetype!r}"
    )
    return response.get_json()


def _html(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, (
        f"GET {path} returned {response.status_code}, expected 200"
    )
    return response.get_data(as_text=True)


def _first_recipe() -> dict:
    recipes = _recipes()
    assert recipes, "the recipe fixture must not be empty"
    return recipes[0]


# --------------------------------------------------------------------------- #
# GET /api/recipes  (C_API_RECIPES)
# --------------------------------------------------------------------------- #
def test_api_recipes_returns_the_whole_collection_in_order(client):
    response = client.get("/api/recipes")
    assert response.status_code == 200
    payload = _json(response)
    expected = _recipes()
    assert isinstance(payload, list)
    assert [item["id"] for item in payload] == [r["id"] for r in expected], (
        "GET /api/recipes must return every recipe in collection order"
    )
    assert payload == expected, (
        "GET /api/recipes must return complete recipe objects with their stored fields"
    )


def test_api_recipes_filters_by_q_across_every_searchable_field(client):
    recipes = _recipes()
    target = recipes[0]
    queries = [
        target["title"],
        f"  {target['title'].upper()}  ",
        target["category"],
        target["ingredients"][0],
    ]
    if target["dietary_tags"]:
        queries.append(target["dietary_tags"][0])

    for query in queries:
        payload = _json(client.get("/api/recipes", query_string={"q": query}))
        expected = [
            recipe["id"]
            for recipe in recipes
            if query.strip().casefold() in _searchable_text(recipe)
        ]
        assert [item["id"] for item in payload] == expected, (
            f"GET /api/recipes?q={query!r} must use the shared match predicate"
        )
        assert target["id"] in [item["id"] for item in payload], (
            f"query {query!r} must still match {target['id']!r}"
        )


def test_api_recipes_with_an_unmatched_query_is_200_with_an_empty_array(client):
    response = client.get("/api/recipes", query_string={"q": "zzz-no-such-dish-zzz"})
    assert response.status_code == 200, (
        "an unmatched query is not an error; it must return 200"
    )
    assert _json(response) == []


def test_api_recipes_with_an_empty_query_returns_everything(client):
    payload = _json(client.get("/api/recipes", query_string={"q": "   "}))
    assert len(payload) == len(_recipes())


# --------------------------------------------------------------------------- #
# GET /api/recipes/<recipe_id>  (C_API_RECIPE)
# --------------------------------------------------------------------------- #
def test_api_recipe_returns_the_single_complete_recipe(client):
    recipe = _first_recipe()
    response = client.get(f"/api/recipes/{recipe['id']}")
    assert response.status_code == 200
    assert _json(response) == recipe


def test_api_recipe_unknown_id_is_404_with_the_exact_error_body(client):
    response = client.get(f"/api/recipes/{UNKNOWN_ID}")
    assert response.status_code == 404
    assert _json(response) == RECIPE_NOT_FOUND, (
        'the body must be exactly {"error": "Recipe not found"}'
    )


# --------------------------------------------------------------------------- #
# Cookbook endpoints  (C_API_COOKBOOK)
# --------------------------------------------------------------------------- #
def test_cookbook_starts_empty(client):
    response = client.get("/api/cookbook")
    assert response.status_code == 200
    assert _json(response) == []


def test_cookbook_round_trip_saves_lists_and_removes(client):
    first, second = _recipes()[0], _recipes()[1]

    created = client.post("/api/cookbook", json={"id": first["id"]})
    assert created.status_code == 201, "a valid save must answer 201"
    body = _json(created)
    assert body.get("recipe_ids") == [first["id"]], (
        "POST /api/cookbook must return the saved ids under 'recipe_ids'"
    )
    assert "movie_ids" not in body and "ids" not in body

    saved = _json(client.get("/api/cookbook"))
    assert saved == [first], (
        "GET /api/cookbook must return the complete saved recipe objects"
    )

    assert client.post("/api/cookbook", json={"id": second["id"]}).status_code == 201
    assert [r["id"] for r in _json(client.get("/api/cookbook"))] == [
        first["id"],
        second["id"],
    ]

    removed = client.delete(f"/api/cookbook/{first['id']}")
    assert removed.status_code == 200
    assert _json(removed).get("recipe_ids") == [second["id"]], (
        "DELETE must return the remaining ids under 'recipe_ids'"
    )
    assert [r["id"] for r in _json(client.get("/api/cookbook"))] == [second["id"]]


def test_repeating_a_delete_still_succeeds(client):
    recipe = _first_recipe()
    assert client.post("/api/cookbook", json={"id": recipe["id"]}).status_code == 201
    assert client.delete(f"/api/cookbook/{recipe['id']}").status_code == 200

    again = client.delete(f"/api/cookbook/{recipe['id']}")
    assert again.status_code == 200, (
        "DELETE must succeed even when the recipe was already absent"
    )
    assert _json(again).get("recipe_ids") == []


def test_deleting_an_id_that_never_existed_succeeds(client):
    response = client.delete(f"/api/cookbook/{UNKNOWN_ID}")
    assert response.status_code == 200
    assert _json(response).get("recipe_ids") == []


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"json": {"id": UNKNOWN_ID}}, id="unknown-id"),
        pytest.param({"json": {}}, id="body-without-id"),
        pytest.param(
            {"data": "{not valid json", "content_type": "application/json"},
            id="malformed-json",
        ),
        pytest.param({}, id="missing-body"),
    ],
)
def test_saving_a_bad_request_is_400_with_recipe_domain_wording(client, kwargs):
    response = client.post("/api/cookbook", **kwargs)
    assert response.status_code == 400, (
        f"POST /api/cookbook with {kwargs!r} must answer 400, "
        f"got {response.status_code}"
    )
    body = _json(response)
    message = str(body.get("error", ""))
    assert message.strip(), "the 400 body must carry an 'error' message"
    assert not CINEMA_TERMS.search(message), (
        f"error message {message!r} uses cinema-domain vocabulary"
    )
    assert re.search(r"recipe|cookbook|dish", message, re.IGNORECASE), (
        f"error message {message!r} must use recipe-domain wording"
    )


def test_a_rejected_save_does_not_enter_the_cookbook(client):
    assert client.post("/api/cookbook", json={"id": UNKNOWN_ID}).status_code == 400
    assert _json(client.get("/api/cookbook")) == []


def test_each_app_owns_an_isolated_cookbook(client):
    """One store per create_app call, so saved state never leaks between apps."""
    recipe = _first_recipe()
    assert client.post("/api/cookbook", json={"id": recipe["id"]}).status_code == 201

    other = _attr("app", "create_app")(testing=True).test_client()
    assert _json(other.get("/api/cookbook")) == [], (
        "a second application must start with an empty cookbook"
    )


# --------------------------------------------------------------------------- #
# GET /api/rails  (C_API_RAILS)
# --------------------------------------------------------------------------- #
def test_api_rails_returns_the_four_named_groups_with_recipe_ids(client):
    response = client.get("/api/rails")
    assert response.status_code == 200
    payload = _json(response)
    rails = payload["rails"] if isinstance(payload, dict) else payload
    assert isinstance(rails, list)
    assert [rail["name"] for rail in rails] == list(RAIL_NAMES)

    known = {recipe["id"] for recipe in _recipes()}
    for rail in rails:
        assert "recipe_ids" in rail, f"rail {rail['name']!r} must expose 'recipe_ids'"
        assert "movie_ids" not in rail
        assert "recipes" not in rail, (
            "the resolved recipe objects are template-only and must be dropped "
            "from the rails payload"
        )
        for recipe_id in rail["recipe_ids"]:
            assert recipe_id in known


def test_api_rails_cookbook_group_reflects_the_saved_collection(client):
    recipe = _first_recipe()
    assert client.post("/api/cookbook", json={"id": recipe["id"]}).status_code == 201

    payload = _json(client.get("/api/rails"))
    rails = payload["rails"] if isinstance(payload, dict) else payload
    by_name = {rail["name"]: rail for rail in rails}
    assert by_name["My Cookbook"]["recipe_ids"] == [recipe["id"]]


def test_no_supported_json_response_contains_a_cinema_domain_key(client):
    recipe = _first_recipe()
    client.post("/api/cookbook", json={"id": recipe["id"]})
    for path in (
        "/api/recipes",
        f"/api/recipes/{recipe['id']}",
        "/api/cookbook",
        "/api/rails",
    ):
        raw = client.get(path).get_data(as_text=True)
        assert "movie_ids" not in raw, f"{path} exposes a movie_ids key"
        for key in re.findall(r'"([A-Za-z0-9_]+)"\s*:', raw):
            assert not CINEMA_TERMS.search(key), (
                f"{path} exposes cinema-domain key {key!r}"
            )


# --------------------------------------------------------------------------- #
# GET /  (C_PAGE_BROWSE)
# --------------------------------------------------------------------------- #
def test_browse_renders_one_card_per_recipe_keyed_to_the_collection_length(client):
    html = _html(client, "/")
    recipes = _recipes()

    links = re.findall(r'href="(/recipe/[^"#?]+)', html)
    assert len(links) == len(recipes), (
        f"GET / rendered {len(links)} recipe links for "
        f"{len(recipes)} recipes in the collection"
    )
    assert sorted(links) == sorted(f"/recipe/{r['id']}" for r in recipes)


def test_browse_cards_carry_total_time_difficulty_and_a_category_or_dietary_label(client):
    html = _html(client, "/")
    for recipe in _recipes():
        total = _total_minutes(recipe)
        assert re.search(rf"\b{total}\b", html), (
            f"{recipe['id']!r} must show its total time of {total} minutes "
            "(prep_minutes + cook_minutes)"
        )
        assert recipe["difficulty"] in html, (
            f"{recipe['id']!r} must show its difficulty"
        )
        labels = [recipe["category"], *recipe["dietary_tags"]]
        assert any(label in html for label in labels), (
            f"{recipe['id']!r} must show at least one category or dietary label"
        )


def test_browse_card_artwork_uses_the_two_recipe_colours_as_css_custom_properties(client):
    html = _html(client, "/")
    for recipe in _recipes():
        for color in recipe["colors"]:
            assert re.search(rf"--[a-z-]+:\s*{re.escape(color)}", html), (
                f"{recipe['id']!r} must expose colour {color!r} as a CSS custom "
                "property so the artwork needs no network image"
            )


def test_browse_shows_the_brand_mark_the_tagline_and_the_match_count(client):
    html = _html(client, "/")
    assert "TableStory" in html
    assert re.search(r'<a\b[^>]*href="/"', html), (
        "the brand mark must link to the browse page"
    )
    assert TAGLINE in html, f"the exact tagline {TAGLINE!r} must be rendered"
    assert re.search(r"\b(cook|kitchen|everyday|meal|dinner|recipe)", html, re.I), (
        "the hero must carry a short everyday-cooking sentence"
    )
    count = len(_recipes())
    assert re.search(rf"\b{count}\s+recipes?\b", html, re.IGNORECASE), (
        f"the match count must read {count} recipes"
    )


def test_browse_search_field_uses_recipe_domain_wording(client):
    html = _html(client, "/")
    inputs = re.findall(r"<input\b[^>]*>", html, re.IGNORECASE)
    searches = [tag for tag in inputs if 'type="search"' in tag or "search" in tag]
    assert searches, "the browse page must render a search field"
    for tag in searches:
        assert not CINEMA_TERMS.search(tag), (
            f"search field {tag!r} uses cinema-domain wording"
        )
    assert re.search(r"recipe|ingredient|dish", " ".join(searches), re.IGNORECASE), (
        "the search field must use recipe-domain wording"
    )


def test_browse_renders_the_exact_empty_state_hidden(client):
    html = _html(client, "/")
    index = html.find(EMPTY_STATE)
    assert index != -1, f"the exact empty state {EMPTY_STATE!r} must be rendered"

    before = html[:index]
    open_tag_start = before.rfind("<")
    assert open_tag_start != -1
    enclosing = before[open_tag_start:]
    assert "hidden" in enclosing, (
        "the empty state must be rendered but hidden, so the client only "
        f"toggles its visibility; enclosing markup was {enclosing!r}"
    )


def test_browse_navigation_is_browse_only_with_no_watchlist_or_profile(client):
    html = _html(client, "/")
    assert "#watchlist" not in html, "the '#watchlist' navigation entry must be deleted"
    assert "#profile" not in html, "the '#profile' navigation entry must be deleted"
    assert not re.search(r'class="[^"]*\bavatar\b', html), (
        "the profile avatar must be deleted rather than rebranded"
    )
    assert not re.search(r"(?i)profile", html), (
        "no profile affordance may remain on the browse page"
    )


def test_no_rendered_page_uses_cinema_domain_wording(client):
    recipe = _first_recipe()
    for path in ("/", f"/recipe/{recipe['id']}"):
        html = _html(client, path)
        match = CINEMA_TERMS.search(html)
        assert match is None, (
            f"{path} still renders cinema-domain wording {match.group(0)!r}"
        )


# --------------------------------------------------------------------------- #
# GET /recipe/<recipe_id>  (C_PAGE_DETAIL)
# --------------------------------------------------------------------------- #
def test_every_recipe_page_returns_200(client):
    for recipe in _recipes():
        response = client.get(f"/recipe/{recipe['id']}")
        assert response.status_code == 200, (
            f"/recipe/{recipe['id']} returned {response.status_code}"
        )


def test_recipe_page_shows_the_title_description_and_a_back_action_to_browse(client):
    recipe = _first_recipe()
    html = _html(client, f"/recipe/{recipe['id']}")
    assert recipe["title"] in html
    assert recipe["description"] in html
    assert re.search(r'<a\b[^>]*href="/"[^>]*>', html), (
        "the recipe page must offer a back action to the browse page"
    )


def test_recipe_page_unknown_id_returns_404(client):
    assert client.get(f"/recipe/{UNKNOWN_ID}").status_code == 404


# --------------------------------------------------------------------------- #
# Legacy cutover  (C_LEGACY_GONE, FN_TEST_LEGACY_GONE)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method,path", LEGACY_ROUTES, ids=lambda v: str(v))
def test_the_cinema_routes_are_gone(client, method, path):
    response = client.open(path, method=method)
    assert response.status_code == 404, (
        f"{method} {path} answered {response.status_code}; the cinema surface must "
        "return 404 with no alias, redirect or compatibility shim"
    )


def test_no_route_rule_mentions_the_cinema_surface(client):
    rules = [str(rule) for rule in client.application.url_map.iter_rules()]
    for rule in rules:
        assert not CINEMA_TERMS.search(rule), (
            f"the app still registers a cinema-domain rule {rule!r}"
        )


def test_the_app_registers_exactly_the_supported_route_surface(client):
    rules = {
        str(rule)
        for rule in client.application.url_map.iter_rules()
        if str(rule) != "/static/<path:filename>"
    }
    expected = {
        "/",
        "/recipe/<recipe_id>",
        "/api/recipes",
        "/api/recipes/<recipe_id>",
        "/api/cookbook",
        "/api/cookbook/<recipe_id>",
        "/api/rails",
    }
    assert rules == expected, (
        "the app must register exactly the two page routes and the six supported "
        f"JSON endpoints; found {sorted(rules)}"
    )


# --------------------------------------------------------------------------- #
# Deleted files and the non-empty JS test directory
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("relative", DELETED_PATHS)
def test_the_legacy_file_is_deleted(relative):
    assert not (DEMO_APP / relative).exists(), (
        f"demo-app/{relative} must be deleted in this change"
    )


def test_the_replacement_templates_and_modules_exist():
    for relative in (
        "app.py",
        "api_routes.py",
        "page_routes.py",
        "templates/browse.html",
        "templates/recipe.html",
        "static/browse-logic.js",
    ):
        assert (DEMO_APP / relative).is_file(), f"ticket #3 requires demo-app/{relative}"

    partials = DEMO_APP / "templates" / "_partials"
    assert partials.is_dir(), "ticket #3 requires demo-app/templates/_partials/"
    assert list(partials.glob("*.html")), (
        "the shared card and save-control partials must live under _partials/"
    )


def test_the_js_test_directory_still_holds_at_least_one_test_file():
    """The configured node gate globs *.test.js; it must always match a file."""
    found = sorted(p.name for p in (DEMO_APP / "static" / "tests").glob("*.test.js"))
    assert found, (
        "demo-app/static/tests must contain at least one *.test.js file at every "
        "point in the change, or `node --test demo-app/static/tests/*.test.js` "
        "matches nothing"
    )


def test_no_static_asset_targets_a_cinema_era_endpoint():
    for path in sorted((DEMO_APP / "static").rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("/api/watchlist", "/api/movies", "/movie/"):
            assert forbidden not in text, (
                f"{path.relative_to(DEMO_APP)} still targets {forbidden}"
            )


def test_no_new_dependency_is_introduced():
    requirements = (DEMO_APP / "requirements.txt").read_text(encoding="utf-8")
    names = {
        re.split(r"[<>=!\[ ]", line.strip())[0].lower()
        for line in requirements.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert names == {"flask", "pytest"}, (
        f"requirements.txt must gain no dependency; found {sorted(names)}"
    )

    package = json.loads((DEMO_APP / "package.json").read_text(encoding="utf-8"))
    assert package.get("type") == "module", "package.json must keep type=module"
    assert not package.get("dependencies")
    assert not package.get("devDependencies")


def test_app_py_holds_no_domain_logic_and_no_cinema_surface():
    text = (DEMO_APP / "app.py").read_text(encoding="utf-8")
    assert "WATCHLIST" not in text, "app.config['WATCHLIST'] must be gone"
    for forbidden in ("/movie/", "/api/movies", "/api/watchlist", "catalog.json"):
        assert forbidden not in text, f"app.py must not mention {forbidden}"
    for helper in ("register_pages", "register_api", "load_recipes", "CookbookStore"):
        assert helper in text, f"create_app must delegate to {helper}"

    signature = inspect.signature(_attr("app", "create_app"))
    assert list(signature.parameters) == ["testing"], (
        "create_app's signature must stay create_app(testing=False)"
    )
    assert signature.parameters["testing"].default is False


# --------------------------------------------------------------------------- #
# Pure context builders  (FN_BROWSE_CONTEXT, FN_CARD_VIEW, FN_SAVE_CONTROL_LABEL)
# --------------------------------------------------------------------------- #
def _view_mode():
    return {"mode": "mobile", "source": "default"}


def _card_view(recipe, saved_ids=()):
    card_view = _attr("page_routes", "card_view")
    return _call_by_parameter_name(
        card_view,
        recipe=recipe,
        saved_ids=list(saved_ids),
        view_mode=_view_mode(),
    )


def _control_label(title: str, saved: bool) -> str:
    label = _attr("page_routes", "cookbook_control_label", "save_control_label")
    return _call_by_parameter_name(label, title=title, saved=saved)


def test_save_control_label_states_the_add_and_remove_action_for_the_named_recipe():
    recipe = _first_recipe()
    assert _control_label(recipe["title"], False) == (
        f"Add {recipe['title']} to My Cookbook"
    )
    assert _control_label(recipe["title"], True) == (
        f"Remove {recipe['title']} from My Cookbook"
    )


def test_card_view_carries_the_card_facts_the_template_needs():
    recipe = _recipes()[1]
    card = _flatten(_card_view(recipe))

    total = _total_minutes(recipe)
    assert total in _values(card), f"the card view must carry the total time {total}"

    values = [value for value in _values(card) if isinstance(value, str)]
    assert recipe["difficulty"] in values
    assert any(
        label in values for label in [recipe["category"], *recipe["dietary_tags"]]
    ), "the card view must carry a category or dietary label"
    assert _searchable_text(recipe) in values, (
        "the card view must carry the server-folded searchable text so the client "
        "filter reads the same fields as GET /api/recipes"
    )
    assert f"/recipe/{recipe['id']}" in values, (
        "the card view must carry the detail href"
    )
    assert recipe["title"][0].upper() in values, (
        "the card view must carry the artwork initial"
    )
    for color in recipe["colors"]:
        assert color in values, "the card view must carry both artwork colours"
    assert f"Add {recipe['title']} to My Cookbook" in values


def test_card_view_reports_the_saved_state_in_its_control_label():
    recipe = _first_recipe()
    card = _flatten(_card_view(recipe, saved_ids=[recipe["id"]]))
    values = [value for value in _values(card) if isinstance(value, str)]
    assert f"Remove {recipe['title']} from My Cookbook" in values, (
        "a saved recipe's card control must state the remove action"
    )


def test_browse_context_supplies_one_card_per_recipe_and_the_match_count():
    collection = _collection()
    store = _store(collection)
    context = _call_by_parameter_name(
        _attr("page_routes", "browse_context"),
        collection=collection,
        store=store,
        view_mode=_view_mode(),
    )
    flat = _flatten(context)

    card_lists = [
        value
        for value in flat.values()
        if isinstance(value, list) and len(value) == len(collection.recipes)
    ]
    assert card_lists, (
        "browse_context must supply one card view per recipe "
        f"({len(collection.recipes)} cards)"
    )
    assert len(collection.recipes) in _values(context), (
        "browse_context must supply the match count"
    )


# --------------------------------------------------------------------------- #
# FN_DETAIL_CONTEXT: the full detail data this ticket owns, whose rendering
# T-DETAIL delivers. No assertion here is weakened for that deferral.
# --------------------------------------------------------------------------- #
def _detail_context(recipe, saved_ids=()):
    collection = _collection()
    store = _store(collection)
    for recipe_id in saved_ids:
        store.add(recipe_id)
    return _call_by_parameter_name(
        _attr("page_routes", "detail_context"),
        recipe=recipe,
        store=store,
        view_mode=_view_mode(),
    )


def test_detail_context_supplies_all_nine_attributes():
    recipe = _recipes()[2]
    flat = _flatten(_detail_context(recipe))
    values = _values(flat)

    for field in ("title", "description", "category", "difficulty"):
        assert recipe[field] in values, f"detail_context must supply {field}"
    for field in ("prep_minutes", "cook_minutes", "servings"):
        assert recipe[field] in values, f"detail_context must supply {field}"
    assert recipe["dietary_tags"] in values or all(
        tag in values for tag in recipe["dietary_tags"]
    ), "detail_context must supply the dietary tags"
    assert _total_minutes(recipe) in values, (
        "detail_context must supply the derived total time"
    )


def test_detail_context_supplies_the_ordered_ingredients_and_steps():
    recipe = _recipes()[2]
    values = _values(_detail_context(recipe))
    assert list(recipe["ingredients"]) in values, (
        "detail_context must supply the ingredients in stored order"
    )
    assert list(recipe["steps"]) in values, (
        "detail_context must supply the steps in stored order"
    )


def test_detail_context_supplies_the_state_bearing_control_label_and_back_href():
    recipe = _first_recipe()

    unsaved = [v for v in _values(_detail_context(recipe)) if isinstance(v, str)]
    assert f"Add {recipe['title']} to My Cookbook" in unsaved

    saved = [
        v
        for v in _values(_detail_context(recipe, saved_ids=[recipe["id"]]))
        if isinstance(v, str)
    ]
    assert f"Remove {recipe['title']} from My Cookbook" in saved, (
        "the detail control label must bear the saved state"
    )

    flat = _flatten(_detail_context(recipe))
    back = [
        value
        for key, value in flat.items()
        if "back" in str(key).lower() and isinstance(value, str)
    ]
    assert back, "detail_context must supply a back href"
    assert all(value == "/" for value in back), (
        f"the mobile back href must be the unchanged browse path, got {back!r}"
    )
