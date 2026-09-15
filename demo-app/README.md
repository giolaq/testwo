# TableStory

**Good food, clearly told.** TableStory is a small Flask demo that browses a
recipe collection, saves recipes to **My Cookbook**, and serves the same
collection to a phone-sized browse page and to a ten-foot TV layout.

Everything in this app is recipe-domain: pages, page metadata, accessible
labels and public JSON field names. A terminology guard
(`tests/test_terminology.py`) keeps it that way.

---

## 1. Install

From the repository root, in a fresh checkout:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r demo-app/requirements.txt
```

That installs Flask and pytest. There are no other runtime dependencies, and
the browser code is plain ES modules, so nothing is bundled or transpiled.
Python 3.11 or newer is required (the terminology guard uses a scoped regular
expression flag).

Node is needed only for the client-logic gate (`node --test`, Node 18+).

## 2. Run

```bash
cd demo-app
python app.py
```

The Flask development server listens on port 5000.

### Mobile mode (the default)

Open <http://localhost:5000/> — a single-column browse page: a search box that
filters the already-rendered recipe cards without a reload, a match count, an
empty state, and a save control on each card.

Open a recipe by following a card link, for example
<http://localhost:5000/recipe/golden-oat-porridge>.

### TV mode

Append `?mode=tv` to either page:

- <http://localhost:5000/?mode=tv> — the rails layout (Popular this week, Ready
  in 30 minutes, Vegetarian favourites, My Cookbook), driven by arrow keys and
  Enter.
- <http://localhost:5000/recipe/golden-oat-porridge?mode=tv> — the TV recipe
  detail page, remote-only, with no pointer-dependent control.

`?mode=tv` is the documented entry point, and it wins: one URL per page and both
modes reachable from any browser. A request without that parameter still renders
TV mode when its `User-Agent` carries a recognised TV hint (`SmartTV`,
`GoogleTV`, `AndroidTV`, `AppleTV`, `HbbTV`, `webOS`, `Tizen`, `BRAVIA`, `Roku`,
`VIDAA`, `CrKey` and `Smart-TV`, matched case-insensitively — see
`demo-app/view_mode.py`), so a television reaches the rails layout on its own.
Any unrecognised `mode` value falls back to mobile. To check the hint path from a
terminal:

```bash
curl -s -H 'User-Agent: Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0)' \
  http://localhost:5000/ | grep -o '<title>[^<]*</title>'
# <title>TableStory · recipes on the big screen</title>
```

## 3. API walkthrough

Six endpoints are supported, and only six. Each command below assumes the
server from step 2 is running.

### `GET /api/recipes` → 200

Every recipe as a JSON array. Optional `q` filters by trimmed, case-folded
substring over the title, description, category, dietary tags and ingredients.
An unmatched `q` is still 200, with an empty array.

```bash
curl -s http://localhost:5000/api/recipes | head -c 200
curl -s 'http://localhost:5000/api/recipes?q=%20%20Barley%20%20'
```

### `GET /api/recipes/<recipe_id>` → 200, or 404

One complete recipe. An unknown id answers 404 with exactly this body:

```json
{"error": "Recipe not found"}
```

```bash
curl -s http://localhost:5000/api/recipes/golden-oat-porridge | head -c 200
curl -s -w ' %{http_code}\n' http://localhost:5000/api/recipes/not-a-recipe
```

### `GET /api/cookbook` → 200

The saved recipes, as complete recipe objects, in the order they were saved.
Empty array when nothing is saved.

```bash
curl -s http://localhost:5000/api/cookbook
```

### `POST /api/cookbook` → 201, or 400

Saves a recipe. Body is `{"id": "<recipe_id>"}`. Success answers 201 with the
saved identifiers under the `recipe_ids` key. An unknown id, a missing body or
a malformed body answers 400 with a recipe-domain error message.

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"id": "golden-oat-porridge"}' http://localhost:5000/api/cookbook
curl -s -w ' %{http_code}\n' -X POST -H 'Content-Type: application/json' \
  -d '{"id": "not-a-recipe"}' http://localhost:5000/api/cookbook
```

### `DELETE /api/cookbook/<recipe_id>` → 200

Removes a recipe and answers 200 with the remaining `recipe_ids`. Idempotent:
deleting an absent or unknown id is still 200.

```bash
curl -s -X DELETE http://localhost:5000/api/cookbook/golden-oat-porridge
curl -s -X DELETE http://localhost:5000/api/cookbook/golden-oat-porridge
```

### `GET /api/rails` → 200

The TV rails as `name` plus `recipe_ids` per rail.

```bash
curl -s http://localhost:5000/api/rails
```

Nothing else is served. Any other path answers Flask's default 404.

## 4. Verification gates

Two required gates, run from the repository root:

```bash
python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
```

Two cheaper checks the project also defines:

```bash
python -m compileall -q demo-app
git diff --check
```

### Where the pytest coverage lives

Coverage is spread across per-ticket modules under `demo-app/tests` rather than
one large file, so a reviewer can read the tests for a slice on its own:

| Module | Covers |
| --- | --- |
| `test_recipe_data.py` | loading and validating `recipes.json`, total time |
| `test_cookbook_rails.py` | the My Cookbook store and the rails builder |
| `test_app.py` | the browse page, the six endpoints, no legacy surface |
| `test_recipe_page.py` | the mobile recipe detail page |
| `test_view_mode.py` | `?mode=tv` resolution and the mode-correct links |
| `test_tv_detail.py` | the TV recipe detail page and its remote-only controls |
| `test_parity.py` | server and client search agree over a shared query list |
| `test_terminology.py` | the terminology and partial-rebrand guard |

The `test_ticket_*.py` modules are independent acceptance tests owned by QA;
they are run by the same gate and are not edited by implementation work.

Client logic is covered under `demo-app/static/tests` by `node --test`, which
runs offline with no DOM and no network.

## 5. Manual reviewer checks

Four things the automated gates cannot see. Please confirm them by hand:

1. **TV legibility at 1920x1080.** Open `/?mode=tv` and
   `/recipe/<recipe_id>?mode=tv` in a 1920x1080 viewport and read them from
   roughly ten feet (or at 25% zoom as a proxy). Body text, rail titles and
   control labels must stay legible.
2. **Measured WCAG AA contrast.** Sample the actual rendered colours of body
   text, rail titles, the focused card and the save control with a contrast
   tool. Each pair must measure at least the WCAG AA ratio (4.5:1 for normal
   text, 3:1 for large text). Read the measurement; do not assume it from the
   palette.
3. **Focus is scrolled fully into view.** Walk both TV pages with the arrow
   keys only. At every step the focused element must be scrolled completely
   into view, never half-off an edge, and no TV control may be clipped by the
   safe-area padding or by a rail's overflow.
4. **No horizontal overflow at 375px.** Load both mobile pages at a 375px-wide
   viewport. Nothing may overflow horizontally and no horizontal scrollbar may
   appear.
