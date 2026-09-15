// Acceptance tests for ticket #9, client half of the search-parity contract.
//
// The Python half lives in
// demo-app/tests/test_ticket_9_terminology_parity_and_docs.py and asserts that
// GET /api/recipes?q=... returns exactly the ids below for exactly these
// queries. This file asserts the same query list and the same expected ids
// against the client predicate (FN_JS_MATCH / FN_JS_NORMALISE in
// static/browse-logic.js) over the searchable text the server renders into each
// card, so the Python and JavaScript predicates cannot drift (C_SEARCH_PY /
// C_SEARCH_JS, R15, R18).
//
// Runs offline under node --test: the deterministic recipe fixture is read from
// disk and no server, DOM or network is involved. The module is imported lazily
// so a missing export fails as a behaviour assertion, not as an uncollectable
// module.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const LOGIC_URL = new URL('../browse-logic.js', import.meta.url);
const RECIPES_PATH = fileURLToPath(new URL('../../recipes.json', import.meta.url));

// The five searchable fields, in the order demo-app/recipe_search.py joins them.
const SEARCHABLE_FIELDS = ['title', 'description', 'category', 'dietary_tags', 'ingredients'];

// The shared sample-query list: one query per searchable field, a mixed-case and
// whitespace-padded query, a non-matching query, and the empty query. Identical
// to PARITY_CASES in the Python suite.
const PARITY_CASES = [
  {query: 'weeknight', field: 'title', ids: ['weeknight-salmon-traybake']},
  {query: 'warm start to the day', field: 'description', ids: ['golden-oat-porridge']},
  {
    query: 'DESSERT',
    field: 'category',
    ids: ['dark-chocolate-mousse', 'honey-roast-plums', 'no-bake-peanut-oat-bars'],
  },
  {
    query: ' vegan',
    field: 'dietary_tags',
    ids: [
      'sunrise-berry-smoothie-bowl',
      'lemon-chickpea-salad',
      'slow-simmered-lentil-stew',
      'spiced-butternut-curry',
      'no-bake-peanut-oat-bars',
    ],
  },
  {query: 'GARLIC', field: 'ingredients', ids: ['slow-simmered-lentil-stew']},
  {query: '  Lemon Chickpea  ', field: 'title', ids: ['lemon-chickpea-salad']},
  {query: 'pineapple pizza', field: 'none', ids: []},
  {
    query: '',
    field: 'all',
    ids: [
      'golden-oat-porridge',
      'herb-garden-omelette',
      'sunrise-berry-smoothie-bowl',
      'lemon-chickpea-salad',
      'tomato-basil-toastie',
      'smoked-paprika-chicken-wraps',
      'slow-simmered-lentil-stew',
      'weeknight-salmon-traybake',
      'mushroom-barley-risotto',
      'spiced-butternut-curry',
      'dark-chocolate-mousse',
      'honey-roast-plums',
      'no-bake-peanut-oat-bars',
    ],
  },
];

async function loadLogic() {
  const path = fileURLToPath(LOGIC_URL);
  assert.ok(existsSync(path), `${path} must provide the client search predicate`);
  const module = await import(LOGIC_URL.href);
  for (const name of ['matchesRecipe', 'normaliseQuery']) {
    assert.equal(
      typeof module[name],
      'function',
      `${path} must export ${name}() so search parity is assertable`,
    );
  }
  return module;
}

/** The card search text the server renders: the five fields, joined, case-folded. */
function cardSearchText(recipe) {
  const parts = [];
  for (const field of SEARCHABLE_FIELDS) {
    const value = recipe[field];
    if (typeof value === 'string') {
      parts.push(value);
    } else if (Array.isArray(value)) {
      parts.push(...value.map(String));
    }
  }
  return parts.join(' ').toLowerCase();
}

function loadCards() {
  const recipes = JSON.parse(readFileSync(RECIPES_PATH, 'utf8'));
  assert.ok(Array.isArray(recipes) && recipes.length >= 12, 'the fixture must load');
  return recipes.map((recipe) => ({id: recipe.id, searchText: cardSearchText(recipe)}));
}

test('the shared query list covers every searchable field, padding and a miss', () => {
  const fields = new Set(PARITY_CASES.map((entry) => entry.field));
  for (const field of SEARCHABLE_FIELDS) {
    assert.ok(fields.has(field), `the shared list must include a ${field} query`);
  }
  assert.ok(
    PARITY_CASES.some((entry) => entry.query !== entry.query.trim()),
    'the shared list must include a whitespace-padded query',
  );
  assert.ok(
    PARITY_CASES.some((entry) => entry.query !== entry.query.toLowerCase() && entry.query.trim()),
    'the shared list must include a mixed-case query',
  );
  assert.ok(
    PARITY_CASES.some((entry) => entry.ids.length === 0),
    'the shared list must include a non-matching query',
  );
});

test('the client predicate leaves visible exactly the ids the server returns', async () => {
  const {matchesRecipe} = await loadLogic();
  const cards = loadCards();

  for (const {query, ids} of PARITY_CASES) {
    const visible = cards
      .filter((card) => matchesRecipe(card.searchText, query))
      .map((card) => card.id);
    assert.deepEqual(
      visible,
      ids,
      `client filtering for ${JSON.stringify(query)} left ${JSON.stringify(visible)} ` +
        `visible, but GET /api/recipes?q=... returns ${JSON.stringify(ids)}`,
    );
  }
});

test('normalisation matches the server rule for every shared query', async () => {
  const {normaliseQuery} = await loadLogic();
  for (const {query} of PARITY_CASES) {
    assert.equal(normaliseQuery(query), query.trim().toLowerCase());
  }
  // A non-string q degrades to "match everything", as on the server.
  for (const value of [undefined, null, 42, {}]) {
    assert.equal(normaliseQuery(value), '');
  }
});

test('an absent or non-string query keeps every card visible', async () => {
  const {matchesRecipe} = await loadLogic();
  const cards = loadCards();
  for (const value of ['', '   ', undefined, null]) {
    const visible = cards.filter((card) => matchesRecipe(card.searchText, value));
    assert.equal(
      visible.length,
      cards.length,
      `${JSON.stringify(value)} must leave every card visible`,
    );
  }
});
