"""Acceptance tests for ticket #5: the TableStory brand stylesheet.

Scope is demo-app/static/styles.css (MOD_STYLES / STYLE_BRAND) plus the way that
stylesheet meets the markup the browse surface already renders. The tests read the
stylesheet as text with a small brace-depth parser instead of a CSS engine, so they
stay offline, deterministic and dependency-free, and they drive the Flask test client
for the rendered-surface assertions.

Deliberately not asserted here:
  * The measured contrast table (owned by ticket-5-brand-stylesheet.test.js so the
    WCAG arithmetic lives in exactly one place) - this file only checks token roles.
  * Anything about the TV templates, the mobile detail body, the browse client or the
    TV focus scripts: those surfaces belong to T-CUTOVER, T-DETAIL, T-TVBROWSE,
    T-TVDETAIL and T-MOBCLIENT. No assertion here requires a later slice's markup or
    behaviour to stay absent.
  * Pixel-measured layout at 375px and 1920x1080, screenshots and greyscale proof: no
    headless gate can prove R37/R38, so those stay reviewer evidence. The static
    checks below cover only the stylesheet properties that make the floors possible.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DEMO_APP = Path(__file__).resolve().parents[1]
STYLES = DEMO_APP / "static" / "styles.css"

SURFACE = "#fff8ed"
PRIMARY = "#c9472d"
SAVED = "#3f6b4f"
TEXT = "#26231f"
HIGHLIGHT = "#e9b44c"

# hex -> (role keywords accepted in the custom-property name)
APPROVED_ROLES = {
    SURFACE: ("surface", "cream", "canvas"),
    PRIMARY: ("primary", "action", "active", "accent-warm"),
    SAVED: ("saved", "cookbook", "herb"),
    TEXT: ("text", "ink"),
    HIGHLIGHT: ("highlight", "accent"),
}

# Values and token names from the cinema-era dark palette. None may survive.
LEGACY_VALUES = ("#0d0d12", "#181820", "#c7f36b", "#f7f4ee", "#9999a7", "#282832", "#2a2a34")
LEGACY_TOKENS = ("--paper", "--lime", "--card", "--ink", "--muted")

CINEMA_TERMS = (
    "pocket cinema",
    "movie",
    "film",
    "cinema",
    "watchlist",
    "poster",
    "runtime",
    "rating",
    "genre",
)

# Classes the customer-visible markup already renders. The stylesheet has to style
# the recipe-domain names rather than the cinema-era ones.
RENDERED_CLASSES = (
    "recipe-grid",
    "recipe-card",
    "recipe-artwork",
    "recipe-artwork-initial",
    "save-control",
    "empty-state",
)

NON_COLOUR_CUE_PROPERTIES = (
    "border",
    "border-width",
    "border-style",
    "border-left",
    "box-shadow",
    "font-weight",
    "text-decoration",
    "text-decoration-line",
    "outline",
    "content",
    "transform",
    "padding",
    "letter-spacing",
)

HEX_RE = re.compile(r"#[0-9a-f]{3,8}\b", re.I)
PX_RE = re.compile(r"(-?\d+(?:\.\d+)?)px")


# --------------------------------------------------------------------------- parsing


class Rule:
    def __init__(self, context: str, selector: str, body: str) -> None:
        self.context = context  # "" for top level, otherwise the @media/@supports head
        self.selector = selector
        self.body = body

    @property
    def declarations(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for chunk in _split_declarations(self.body):
            if ":" not in chunk:
                continue
            name, _, value = chunk.partition(":")
            out.append((name.strip().lower(), value.strip()))
        return out

    def value(self, prop: str) -> str | None:
        found = None
        for name, value in self.declarations:
            if name == prop:
                found = value  # last one wins, as in CSS
        return found

    @property
    def is_tv(self) -> bool:
        for width in PX_RE.findall(self.context):
            if float(width) >= 1280:
                return True
        return False


def _split_declarations(body: str) -> list[str]:
    """Split on top-level semicolons only, so var() fallbacks stay intact."""
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def parse_css(text: str) -> list[Rule]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    rules: list[Rule] = []

    def walk(src: str, context: str) -> None:
        head = ""
        i = 0
        while i < len(src):
            ch = src[i]
            if ch == "{":
                depth = 1
                j = i + 1
                while j < len(src) and depth:
                    if src[j] == "{":
                        depth += 1
                    elif src[j] == "}":
                        depth -= 1
                    j += 1
                body = src[i + 1 : j - 1]
                selector = head.strip()
                head = ""
                i = j
                if selector.startswith("@media") or selector.startswith("@supports"):
                    walk(body, f"{context} {selector}".strip())
                else:
                    rules.append(Rule(context, selector, body))
                continue
            if ch == ";" and not head.strip().startswith("@"):
                head = ""
                i += 1
                continue
            if ch == ";":
                head = ""
                i += 1
                continue
            head += ch
            i += 1

    walk(text, "")
    return rules


@pytest.fixture(scope="module")
def css_text() -> str:
    assert STYLES.is_file(), f"expected the brand stylesheet at {STYLES}"
    return STYLES.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rules(css_text: str) -> list[Rule]:
    parsed = parse_css(css_text)
    assert parsed, "the stylesheet defines no rules"
    return parsed


@pytest.fixture(scope="module")
def tokens(rules: list[Rule]) -> dict[str, str]:
    """Custom properties declared on :root, lower-cased."""
    out: dict[str, str] = {}
    for rule in rules:
        if ":root" not in rule.selector.replace(" ", ""):
            continue
        for name, value in rule.declarations:
            if name.startswith("--"):
                out[name] = value.strip().lower()
    assert out, "the stylesheet declares no :root custom properties"
    return out


def resolve(value: str, tokens: dict[str, str], depth: int = 0) -> str:
    """Follow var(--token) chains down to a literal value."""
    value = value.strip().lower()
    match = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,(.*))?\)", value)
    if match and depth < 8:
        name = match.group(1)
        if name in tokens:
            return resolve(tokens[name], tokens, depth + 1)
        if match.group(2):
            return resolve(match.group(2), tokens, depth + 1)
    return value


def relative_luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    channels = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


# ----------------------------------------------------------------- palette and roles


def test_root_defines_the_five_approved_colours_with_role_named_properties(tokens):
    for hex_value, role_words in APPROVED_ROLES.items():
        owners = [name for name, value in tokens.items() if value.startswith(hex_value)]
        assert owners, f"{hex_value} is not declared as a :root custom property"
        assert any(any(word in name for word in role_words) for name in owners), (
            f"{hex_value} is declared as {owners} but no property name states its role "
            f"(expected one of {role_words})"
        )


def test_every_approved_token_is_actually_used_by_a_rule(css_text, tokens, rules):
    for hex_value, role_words in APPROVED_ROLES.items():
        names = [
            name
            for name, value in tokens.items()
            if value.startswith(hex_value) and any(word in name for word in role_words)
        ]
        assert any(f"var({name}" in css_text.replace(" ", "") for name in names), (
            f"the token for {hex_value} ({names}) is defined but never referenced with var()"
        )


def test_no_dark_streaming_surface_or_legacy_token_remains(css_text, tokens, rules):
    lowered = css_text.lower()
    for value in LEGACY_VALUES:
        assert value not in lowered, f"cinema-era colour {value} still present"
    assert not re.search(r"color-scheme\s*:[^;}]*dark", lowered), (
        "the stylesheet still opts into a dark colour scheme"
    )
    for token in LEGACY_TOKENS:
        assert token not in tokens, f"cinema-era token {token} still declared on :root"

    approved = set(APPROVED_ROLES)
    for rule in rules:
        for name, value in rule.declarations:
            if name not in ("background", "background-color"):
                continue
            for literal in HEX_RE.findall(value):
                literal = literal.lower()
                if len(literal) not in (4, 7) or literal in approved:
                    continue
                assert relative_luminance(literal) >= 0.3, (
                    f"{rule.selector} paints a dark surface {literal} "
                    "(luminance below 0.3) outside the approved palette"
                )


def test_body_paints_the_cream_surface_with_charcoal_text(rules, tokens):
    body_rules = [r for r in rules if not r.context and _selects(r.selector, "body")]
    assert body_rules, "no top-level body rule found"
    background = _last_value(body_rules, ("background", "background-color"))
    colour = _last_value(body_rules, ("color",))
    assert background, "the body rule sets no background"
    assert resolve(background, tokens).startswith(SURFACE), (
        f"body background resolves to {resolve(background, tokens)}, expected {SURFACE}"
    )
    assert colour, "the body rule sets no text colour"
    assert resolve(colour, tokens).startswith(TEXT), (
        f"body text colour resolves to {resolve(colour, tokens)}, expected {TEXT}"
    )


def _selects(selector: str, target: str) -> bool:
    return any(part.strip() == target for part in selector.split(","))


def _last_value(rules: list[Rule], props: tuple[str, ...]) -> str | None:
    found = None
    for rule in rules:
        for name, value in rule.declarations:
            if name in props:
                found = value
    return found


# ------------------------------------------------------------------ CSS-only artwork


def test_recipe_artwork_is_generated_from_the_two_recipe_colour_properties(rules):
    artwork = [r for r in rules if "recipe-artwork" in r.selector]
    assert artwork, "no rule styles .recipe-artwork"
    joined = " ".join(r.body for r in artwork).replace(" ", "")
    for prop in ("--artwork-a", "--artwork-b"):
        assert f"var({prop}" in joined, (
            f"the artwork rules never consume {prop}, the custom property the card partial emits"
        )
    paints = any(
        name in ("background", "background-image", "background-color")
        for rule in artwork
        for name, _ in rule.declarations
    )
    assert paints, "the artwork rules never paint a background from those colours"


def test_dish_initial_is_visibly_treated_not_hidden(rules):
    initial = [r for r in rules if "recipe-artwork-initial" in r.selector]
    assert initial, "no rule styles .recipe-artwork-initial"
    declarations = {name: value for r in initial for name, value in r.declarations}
    assert "font-size" in declarations, "the dish initial gets no explicit type treatment"
    assert declarations.get("display", "").strip() != "none", "the dish initial is display:none"
    assert declarations.get("visibility", "").strip() != "hidden", "the dish initial is hidden"
    opacity = declarations.get("opacity")
    if opacity is not None:
        assert float(opacity.strip()) >= 0.5, f"the dish initial is near-invisible (opacity {opacity})"


def test_stylesheet_requests_no_external_font_or_image(css_text):
    lowered = css_text.lower()
    assert "@import" not in lowered, "@import adds a network request"
    assert "@font-face" not in lowered, "@font-face adds an external font"
    for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", lowered):
        assert url.startswith("data:"), f"stylesheet references external media: url({url})"


def test_browse_page_renders_distinct_artwork_colours_for_at_least_six_recipes(client):
    html = client.get("/").get_data(as_text=True)
    signatures = set(
        re.findall(
            r"--artwork-a:\s*([^;\"]+);\s*--artwork-b:\s*([^;\"]+)",
            html,
        )
    )
    initials = re.findall(r'class="recipe-artwork-initial"[^>]*>([^<]+)<', html)
    assert len(signatures) >= 6, (
        f"only {len(signatures)} distinct artwork colour pairs are rendered; "
        "the artwork cannot be visually distinct across six recipes"
    )
    assert len(initials) >= 6, f"only {len(initials)} cards render a dish initial"
    assert all(initial.strip() for initial in initials), "a card renders an empty dish initial"


def test_rendered_pages_request_no_outbound_media(client):
    for path in ("/", "/recipe/golden-oat-porridge"):
        html = client.get(path).get_data(as_text=True)
        assert "<img" not in html.lower(), f"{path} renders an <img> element"
        assert not re.search(r"(src|srcset)\s*=\s*[\"']https?://", html, re.I), (
            f"{path} requests remote media"
        )
        assert not re.search(r"url\(\s*['\"]?https?://", html, re.I), (
            f"{path} references a remote background image"
        )


# --------------------------------------------------------------- saved-state styling


def test_saved_state_styling_hangs_off_the_aria_state_attribute(css_text, rules):
    saved_rules = [r for r in rules if 'aria-pressed="true"' in r.selector.replace("'", '"')]
    assert saved_rules, (
        'no rule selects [aria-pressed="true"]; the saved state must be styled from the '
        "ARIA state attribute rather than a colour-only class"
    )
    assert not re.search(r"\.saved\b", css_text), (
        "the stylesheet still styles a colour-only .saved class"
    )


def test_saved_and_unsaved_controls_differ_by_a_non_colour_cue(rules):
    saved_rules = [r for r in rules if 'aria-pressed="true"' in r.selector.replace("'", '"')]
    assert saved_rules, 'no [aria-pressed="true"] rule to inspect'
    properties = {name for r in saved_rules for name, _ in r.declarations}
    non_colour = properties.intersection(NON_COLOUR_CUE_PROPERTIES)
    assert non_colour, (
        "the saved state only changes colour properties "
        f"({sorted(properties)}); it needs a text or shape cue too"
    )

    cue_rules = [
        r
        for r in rules
        if "save-control-text" in r.selector or "save-control-mark" in r.selector
    ]
    for rule in cue_rules:
        declarations = dict(rule.declarations)
        assert declarations.get("display", "").strip() != "none", (
            f"{rule.selector} hides the non-colour cue the markup renders"
        )
        assert declarations.get("font-size", "1px").strip() not in ("0", "0px"), (
            f"{rule.selector} collapses the non-colour cue to zero size"
        )


def test_browse_control_exposes_the_state_attribute_the_stylesheet_targets(client):
    html = client.get("/").get_data(as_text=True)
    assert 'aria-pressed="false"' in html, "no unsaved control renders an ARIA state attribute"
    assert 'class="save-control-text"' in html, "no textual save cue is rendered"


# ----------------------------------------------------------------------- focus states


def test_focus_ring_is_visible_and_defined_for_both_modes(rules, tokens):
    focus_rules = [r for r in rules if ":focus" in r.selector]
    assert focus_rules, "the stylesheet defines no focus styling"

    base = [r for r in focus_rules if not r.is_tv]
    assert base, "no focus styling outside the TV media query"
    base_width = _outline_width(base)
    assert base_width is not None and base_width >= 2, (
        f"the mobile focus ring is {base_width}px wide; it must be a visible ring (>= 2px)"
    )

    tv_focus = [r for r in focus_rules if r.is_tv]
    assert tv_focus, "no focus styling inside the TV layout, so TV focus contrast is not raised"
    tv_width = _outline_width(tv_focus)
    assert tv_width is not None and tv_width >= base_width, (
        f"the TV focus ring ({tv_width}px) is not at least as strong as the mobile one ({base_width}px)"
    )

    colours = []
    for rule in focus_rules:
        for name, value in rule.declarations:
            if name in ("outline", "outline-color", "box-shadow"):
                for token in re.findall(r"var\(\s*--[\w-]+\s*\)", value):
                    colours.append(resolve(token, tokens))
                colours.extend(m.lower() for m in HEX_RE.findall(value))
    hexes = [c for c in colours if c.startswith("#") and len(c) in (4, 7)]
    assert hexes, "the focus ring has no resolvable colour"
    surface_luminance = relative_luminance(SURFACE)
    for colour in hexes:
        ratio = _contrast(relative_luminance(colour), surface_luminance)
        assert ratio >= 3.0, (
            f"focus ring colour {colour} has only {ratio:.2f}:1 against the cream surface"
        )


def _outline_width(rules: list[Rule]) -> float | None:
    widths: list[float] = []
    for rule in rules:
        for name, value in rule.declarations:
            if name in ("outline", "outline-width"):
                if "none" in value.lower():
                    continue
                found = PX_RE.findall(value)
                if found:
                    widths.append(float(found[0]))
    return max(widths) if widths else None


def _contrast(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_no_element_loses_its_focus_ring_without_a_replacement(rules, css_text):
    focus_text = " ".join(r.selector for r in rules if ":focus" in r.selector)
    for rule in rules:
        for name, value in rule.declarations:
            if name != "outline":
                continue
            if value.strip().lower() not in ("0", "none", "0px"):
                continue
            if ":focus" in rule.selector:
                pytest.fail(f"{rule.selector} removes the focus ring")
            keys = re.findall(r"[.#]([\w-]+)", rule.selector) or rule.selector.split()
            assert any(str(key) in focus_text for key in keys), (
                f"{rule.selector} removes the outline but defines no :focus-visible replacement"
            )


# ------------------------------------------------------------- layout floor and ceiling


def test_mobile_rules_declare_no_fixed_width_wider_than_375_pixels(rules):
    for rule in rules:
        if rule.is_tv:
            continue
        for name, value in rule.declarations:
            if name not in ("width", "min-width"):
                continue
            for width in PX_RE.findall(value):
                assert float(width) <= 375, (
                    f"{rule.selector} fixes {name}:{value.strip()}, which overflows a 375px viewport"
                )


def test_layout_uses_border_box_sizing_and_a_zero_min_track_grid(css_text, rules):
    assert re.search(r"box-sizing\s*:\s*border-box", css_text), (
        "no border-box sizing rule, so padding can push content past 375px"
    )
    grid_rules = [r for r in rules if "recipe-grid" in r.selector or "recipe-card" in r.selector]
    assert grid_rules, "no rule styles the recipe grid"
    templates = [
        value
        for r in grid_rules
        for name, value in r.declarations
        if name in ("grid-template-columns", "grid-template")
    ]
    assert templates, "the recipe grid declares no column template"
    assert any(
        "minmax(0" in t.replace(" ", "") or "auto-fit" in t or "auto-fill" in t for t in templates
    ), f"grid columns {templates} allow min-content overflow at 375px; use minmax(0, ...)"


def test_tv_layout_scales_sizing_and_spacing_within_the_same_brand(rules):
    tv_rules = [r for r in rules if r.is_tv]
    assert tv_rules, "no @media query targets a TV viewport (min-width >= 1280px)"
    properties = {name for r in tv_rules for name, _ in r.declarations}
    assert properties.intersection({"font-size", "line-height"}), (
        "the TV layout never scales type sizing"
    )
    assert properties.intersection({"gap", "padding", "margin", "row-gap", "column-gap"}), (
        "the TV layout never scales spacing"
    )

    approved = set(APPROVED_ROLES)
    for rule in tv_rules:
        for name, value in rule.declarations:
            for literal in HEX_RE.findall(value):
                assert literal.lower() in approved, (
                    f"TV rule {rule.selector} introduces {literal} outside the approved palette, "
                    "so the two modes would not read as one brand"
                )


# ------------------------------------------------------- terminology and no new deps


def test_no_cinema_domain_term_survives_in_the_stylesheet(css_text):
    lowered = css_text.lower()
    for term in CINEMA_TERMS:
        assert not re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", lowered), (
            f"cinema-domain term '{term}' still appears in the stylesheet"
        )


def test_stylesheet_selectors_cover_the_recipe_domain_markup(css_text):
    for class_name in RENDERED_CLASSES:
        assert re.search(rf"\.{re.escape(class_name)}\b", css_text), (
            f"no rule styles the rendered class .{class_name}"
        )


def test_no_dependency_or_build_step_is_added():
    requirements = [
        line.strip()
        for line in (DEMO_APP / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert {r.split(">=")[0].split("==")[0].strip().lower() for r in requirements} == {
        "flask",
        "pytest",
    }, f"requirements.txt gained a dependency: {requirements}"

    package = json.loads((DEMO_APP / "package.json").read_text(encoding="utf-8"))
    assert package.get("type") == "module", "package.json must keep type=module"
    for key in ("dependencies", "devDependencies", "peerDependencies", "scripts"):
        assert key not in package, f"package.json gained a {key} entry"

    for pattern in ("*.config.js", "*.config.cjs", "tailwind.config*", "postcss.config*"):
        assert not list(DEMO_APP.glob(pattern)), f"a build step was added ({pattern})"
