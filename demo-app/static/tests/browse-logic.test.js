// Implementation-owned tests for the browse logic module. Added in the same
// change that deletes app-logic.test.js, so demo-app/static/tests never goes
// empty and `node --test demo-app/static/tests/*.test.js` always matches a file.
// Offline and deterministic: expectations come from the committed fixture.

import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

import {matchesRecipe, normaliseQuery} from '../browse-logic.js';

const FIXTURE_URL = new URL('../../recipes.json', import.meta.url);
const SEARCHABLE_FIELDS = ['title', 'description', 'category', 'dietary_tags', 'ingredients'];

const recipes = JSON.parse(readFileSync(fileURLToPath(FIXTURE_URL), 'utf8'));

// The JavaScript twin of the server's searchable_text().
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

test('normaliseQuery trims and case-folds', () => {
  assert.equal(normaliseQuery('  Lemon CHICKPEA '), 'lemon chickpea');
  assert.equal(normaliseQuery('oat'), 'oat');
  assert.equal(normaliseQuery('\t \n'), '');
});

test('normaliseQuery degrades a non-string to the empty query', () => {
  for (const value of [undefined, null, 7, {}, [], true]) {
    assert.equal(normaliseQuery(value), '');
  }
});

test('an empty query matches every recipe', () => {
  for (const recipe of recipes) {
    assert.equal(matchesRecipe(searchText(recipe), ''), true);
    assert.equal(matchesRecipe(searchText(recipe), '  '), true);
    assert.equal(matchesRecipe(searchText(recipe), undefined), true);
  }
});

test('matching ignores case and surrounding whitespace', () => {
  const [first] = recipes;
  const text = searchText(first);
  assert.equal(matchesRecipe(text, first.title), true);
  assert.equal(matchesRecipe(text, `   ${first.title.toUpperCase()} `), true);
  assert.equal(matchesRecipe(text, 'zzz-no-such-dish-zzz'), false);
});

test('matching spans all five searchable fields', () => {
  for (const field of SEARCHABLE_FIELDS) {
    const recipe = recipes.find((candidate) => {
      const value = candidate[field];
      return typeof value === 'string'
        ? value.trim() !== ''
        : Array.isArray(value) && value.length > 0;
    });
    assert.ok(recipe, `the fixture must contain a recipe with a ${field} value`);
    const raw = recipe[field];
    const query = typeof raw === 'string' ? raw : String(raw[0]);
    assert.equal(matchesRecipe(searchText(recipe), query), true);
  }
});

test('the predicate is plain containment over the folded text', () => {
  const queries = ['', ' ', 'Vegan', 'vegan', '  DESSERT ', 'oat', 'no-such-thing'];
  for (const query of queries) {
    for (const recipe of recipes) {
      const text = searchText(recipe);
      const folded = query.trim().toLowerCase();
      assert.equal(
        matchesRecipe(text, query),
        folded === '' ? true : text.includes(folded),
      );
    }
  }
});
