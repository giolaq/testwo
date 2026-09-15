# TableStory

**Good food, clearly told.** TableStory is a recipe discovery app for home cooks:
browse and search a deterministic local collection of recipes on a phone, save
dishes to My Cookbook, and follow ingredients and numbered method steps on a TV
using only a remote or the keyboard.

Stack: Python, Flask, Jinja templates, one stylesheet and vanilla ES modules. No
frontend framework, no database, no build step, no network access and no secrets
or API keys. All artwork is generated with CSS from two colours per recipe.

---

## 1. Install dependencies

From the repository root, using the project's documented command:

```bash
python -m pip install -r demo-app/requirements.txt
```

That installs Flask and pytest and nothing else. Everything below works offline
after this step. Node.js is needed only for the second verification gate; it has
no packages to install (`demo-app/package.json` declares no dependencies).

## 2. Start the server

```bash
cd demo-app
python app.py
```

The app serves on port 5000 with reloading enabled.

## 3. Open mobile mode

<http://127.0.0.1:5000/> — the default. Designed for a 375 CSS px viewport: the
TableStory brand mark, the tagline, the search field, the matching-recipe count
and one card per recipe showing title, total time (prep + cook), difficulty, a
category or dietary label and a My Cookbook save control. Typing in the search
field filters the cards live, with no page reload. A query with no matches shows
exactly `No recipes found. Try another ingredient or dish.`

Open a card to reach `/recipe/<recipe_id>` for the full metadata, the ingredient
list in stored order and the numbered method steps.

## 4. Open TV mode

<http://127.0.0.1:5000/?mode=tv> — the explicit switch, intended for 1920x1080.
A recognised TV user-agent hint selects the same layout without `?mode=tv`, and
an unrecognised `mode` value falls back to mobile.

TV browse shows four rails: **Popular this week**, **Ready in 30 minutes**,
**Vegetarian favourites** and **My Cookbook**. Navigate with the remote or the
keyboard only:

| Key | TV browse | TV recipe page |
| --- | --- | --- |
| Arrow Left / Right | move between cards in a rail | — |
| Arrow Up / Down | move between rails | move between the back action and the My Cookbook action |
| Enter | open the focused recipe, keeping TV mode | activate the focused action |
| Escape or Backspace | — | return to TV browse |

Every in-app link generated in TV mode keeps `mode=tv`, so the back action from a
TV recipe page returns to TV browse rather than to the phone layout.

## 5. Supported API walkthrough

Exactly six public endpoints. Saved recipes live in process memory only and reset
when the server restarts.

| Request | Expected | Notes |
| --- | --- | --- |
| `GET /api/recipes` | `200` | The whole collection, in fixture order. |
| `GET /api/recipes?q=lemon` | `200` | Same matching rule as the browse search: case-insensitive containment over title, description, category, dietary tags and ingredient text. An unmatched query returns `200` with `[]`. |
| `GET /api/recipes/<recipe_id>` | `200` | One recipe. |
| `GET /api/recipes/not-a-recipe` | `404` | Body is exactly `{"error": "Recipe not found"}`. |
| `GET /api/cookbook` | `200` | The complete saved recipe objects. |
| `POST /api/cookbook` with `{"id": "<recipe_id>"}` | `201` | Returns the saved ids under `recipe_ids`. |
| `POST /api/cookbook` with an unknown id, or a missing or malformed body | `400` | Recipe-domain error message. |
| `DELETE /api/cookbook/<recipe_id>` | `200` | Returns the remaining `recipe_ids`; repeating the same delete still succeeds. |
| `GET /api/rails` | `200` | The four named groups, each exposing `recipe_ids`. |

Copy-paste walkthrough (server running, `ID` = any id from `GET /api/recipes`):

```bash
curl -s localhost:5000/api/recipes | head -c 400
curl -s "localhost:5000/api/recipes?q=lemon"
curl -s -o /dev/null -w '%{http_code}\n' localhost:5000/api/recipes/$ID      # 200
curl -s -w '\n%{http_code}\n' localhost:5000/api/recipes/not-a-recipe        # {"error": "Recipe not found"} 404
curl -s -X POST localhost:5000/api/cookbook -H 'Content-Type: application/json' -d "{\"id\": \"$ID\"}" -w '\n%{http_code}\n'   # 201
curl -s localhost:5000/api/cookbook
curl -s -X DELETE localhost:5000/api/cookbook/$ID -w '\n%{http_code}\n'      # 200
curl -s -X DELETE localhost:5000/api/cookbook/$ID -w '\n%{http_code}\n'      # 200 again: delete is idempotent
curl -s localhost:5000/api/rails
```

Nothing else is supported. The legacy paths of the app this was rebranded from —
`/movie/<id>`, `/api/movies`, `/api/movies/<id>` and every `/api/watchlist` path —
are removed with no redirect, alias or compatibility shim, and answer `404`:

```bash
for p in /movie/afterlight /api/movies /api/movies/afterlight /api/watchlist; do
  curl -s -o /dev/null -w "$p %{http_code}\n" localhost:5000$p               # each 404
done
```

## 6. Verification gates

Both gates are required, run offline after the install above, and must never be
skipped or weakened:

```bash
python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
```

Advisory: `python -m compileall -q demo-app`. Repository integrity:
`git diff --check`.

### Where each area is asserted

pytest coverage is spread across per-ticket modules under `demo-app/tests`:

| Module | Area |
| --- | --- |
| `test_recipe_data.py` | Recipe fixture loading, the thirteen field rules and the content mix. |
| `test_cookbook_rails.py` | My Cookbook store and endpoints, rail composition and the saved-state rail. |
| `test_app.py` | App factory, the six supported endpoints, and the removed legacy paths answering 404. |
| `test_recipe_page.py` | `GET /recipe/<recipe_id>`: metadata, ordered ingredients, numbered steps, save control, 404. |
| `test_view_mode.py` | Mode resolution (`?mode=tv`, user-agent hints, fallback) and mode retention in links. |
| `test_tv_detail.py` | TV recipe page layout and the TV back / My Cookbook actions. |
| `test_parity.py` | Server/client search parity over the shared sample-query list. |
| `test_terminology.py` | The terminology and partial-rebrand guard over the whole supported surface. |

The modules named `test_ticket_*.py` are the per-ticket acceptance suites and
cover the same areas independently. Client-side logic is asserted by
`demo-app/static/tests/*.test.js`, which import the dependency-free modules
(`browse-logic.js`, `tv-logic.js`) with no DOM and no network.

## 7. Manual reviewer checks

These cannot be proven by a headless gate and must be walked through by hand
before the work is called done:

1. **TV legibility at 1920x1080.** Open `/?mode=tv` and a TV recipe page in a
   1920x1080 viewport and confirm titles, metadata, ingredients and steps are
   readable at television viewing distance.
2. **Measured contrast.** Measure the WCAG AA contrast of body text, metadata,
   the save control in both states and the focus treatment with a contrast tool
   (not by eye): 4.5:1 for normal text, 3:1 for large text and for interface
   components. The computed table lives at the top of
   `demo-app/static/styles.css`.
3. **Focus scrolled fully into view.** In TV browse, move focus to the first and
   the last card of every rail and confirm the focused card is scrolled entirely
   into view and keeps its high-contrast focus treatment.
4. **No clipped TV controls.** At 1920x1080, confirm no rail heading, card or TV
   action is clipped by the viewport edge.
5. **No horizontal overflow at 375px.** At a 375 CSS px viewport, confirm the
   browse page and the recipe page produce no horizontal page scrolling, with
   long ingredient and step text wrapping instead.
6. **Save state without colour.** Confirm saved and unsaved controls differ by
   label and by a non-colour cue, on browse cards and on the recipe page, in
   both modes.
