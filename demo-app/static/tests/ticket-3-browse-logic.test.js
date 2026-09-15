// Acceptance tests for ticket #3: the browse logic module that replaces the
// cinema-era logic module.
//
// Scope is demo-app/static/browse-logic.js (MOD_BROWSE_LOGIC) and only the two
// pure helpers this ticket owns: FN_JS_NORMALISE and FN_JS_MATCH. The DOM
// binding, the cookbook toggle and the count/empty-state helpers land in
// T-MOBCLIENT and are deliberately not asserted here.
//
// The module is imported lazily behind a file-existence assertion so a missing
// module fails as a behaviour assertion rather than as an unhandled module
// resolution error. Everything is offline and deterministic: the expectations
// are derived from the committed recipe fixture.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const MODULE_URL = new URL('../browse-logic.js', import.meta.url);
const FIXTURE_URL = new URL('../../recipes.json', import.meta.url);

const SEARCHABLE_FIELDS = ['title', 'description', 'category', 'dietary_tags', 'ingredients'];

async function browseLogic() {
  assert.ok(
    existsSync(fileURLToPath(MODULE_URL)),
    'ticket #3 must add demo-app/static/browse-logic.js as the successor to the deleted logic module',
  );
  const module = await import(MODULE_URL.href);
  for (const name of ['normaliseQuery', 'matchesRecipe']) {
    assert.equal(
      typeof module[name],
      'function',
      `browse-logic.js must export ${name}()`,
    );
  }
  return module;
}

function recipes() {
  return JSON.parse(readFileSync(fileURLToPath(FIXTURE_URL), 'utf8'));
}

// The JavaScript twin of the server's searchable_text(): the same five fields,
// joined with single spaces and case-folded. Mirroring it here is what makes a
// drift between the two implementations visible.
function searchText(recipe) {
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

test('normaliseQuery trims and case-folds', async () => {
  const {normaliseQuery} = await browseLogic();
  assert.equal(normaliseQuery('  Golden OAT  '), 'golden oat');
  assert.equal(normaliseQuery('chickpea'), 'chickpea');
  assert.equal(normaliseQuery('   '), '');
});

test('normaliseQuery treats a missing or non-string value as an empty query', async () => {
  const {normaliseQuery} = await browseLogic();
  for (const value of [undefined, null, 42, {}, []]) {
    assert.equal(
      normaliseQuery(value),
      '',
      `normaliseQuery(${JSON.stringify(value) ?? String(value)}) must degrade to the empty query`,
    );
  }
});

test('an empty query matches every card', async () => {
  const {matchesRecipe} = await browseLogic();
  for (const recipe of recipes()) {
    assert.equal(matchesRecipe(searchText(recipe), ''), true);
    assert.equal(matchesRecipe(searchText(recipe), '   '), true);
    assert.equal(matchesRecipe(searchText(recipe), undefined), true);
  }
});

test('matching ignores case and surrounding whitespace', async () => {
  const {matchesRecipe} = await browseLogic();
  const [first] = recipes();
  const text = searchText(first);

  assert.equal(matchesRecipe(text, first.title), true);
  assert.equal(matchesRecipe(text, `  ${first.title.toUpperCase()}  `), true);
  assert.equal(matchesRecipe(text, 'zzz-no-such-dish-zzz'), false);
});

test('matching spans title, description, category, dietary tags and ingredients', async () => {
  const {matchesRecipe} = await browseLogic();
  const all = recipes();

  for (const field of SEARCHABLE_FIELDS) {
    const recipe = all.find((candidate) => {
      const value = candidate[field];
      return typeof value === 'string' ? value.trim() !== '' : Array.isArray(value) && value.length > 0;
    });
    assert.ok(recipe, `the fixture must contain a recipe with a ${field} value`);
    const raw = recipe[field];
    const query = typeof raw === 'string' ? raw : String(raw[0]);
    assert.equal(
      matchesRecipe(searchText(recipe), query),
      true,
      `a query drawn from ${field} must match its own recipe`,
    );
  }
});

test('the predicate agrees with the server rule on every recipe and query', async () => {
  const {matchesRecipe} = await browseLogic();
  const all = recipes();
  const queries = [
    '',
    '  ',
    'Vegan',
    'vegan',
    '  BREAKFAST ',
    'lemon',
    'oat',
    'zzz-no-such-dish-zzz',
  ];

  for (const query of queries) {
    for (const recipe of all) {
      const text = searchText(recipe);
      const folded = query.trim().toLowerCase();
      const expected = folded === '' ? true : text.includes(folded);
      assert.equal(
        matchesRecipe(text, query),
        expected,
        `matchesRecipe(${recipe.id}, ${JSON.stringify(query)}) must equal the shared containment rule`,
      );
    }
  }
});

test('the cinema-era logic module and its tests are deleted', async () => {
  for (const relative of ['../app-logic.js', '../app.js', './app-logic.test.js']) {
    assert.equal(
      existsSync(fileURLToPath(new URL(relative, import.meta.url))),
      false,
      `${relative.replace(/^\.\.?\//, '')} must be deleted in this change so no film fixture survives`,
    );
  }
});
