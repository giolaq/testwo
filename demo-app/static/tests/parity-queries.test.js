// The client half of FN_TEST_PARITY: the shared sample-query list that
// demo-app/tests/test_parity.py runs through GET /api/recipes?q=... asserted
// here against matchesRecipe(), so the Python and JavaScript predicates cannot
// drift. Runs offline under node --test with no DOM and no network.

import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

import {matchesRecipe, normaliseQuery} from '../browse-logic.js';

const RECIPES_URL = new URL('../../recipes.json', import.meta.url);

// The five searchable fields, in the order demo-app/recipe_search.py folds them.
const SEARCHABLE_FIELDS = [
  'title',
  'description',
  'category',
  'dietary_tags',
  'ingredients',
];

// The shared sample-query list, identical to SHARED_QUERIES in
// demo-app/tests/test_parity.py: mixed case, whitespace padded, one query per
// searchable field and one query that matches nothing.
const SHARED_QUERIES = [
  'Porridge',
  'spoonful',
  'Dessert',
  'Vegan',
  '  almonds  ',
  '  Barley  ',
  'Sourdough Starter',
];

function recipes() {
  return JSON.parse(readFileSync(RECIPES_URL, 'utf8'));
}

function searchableText(recipe) {
  const parts = [];
  for (const field of SEARCHABLE_FIELDS) {
    const value = recipe[field];
    if (Array.isArray(value)) {
      parts.push(...value.map(String));
    } else if (typeof value === 'string') {
      parts.push(value);
    }
  }
  return parts.join(' ').toLowerCase();
}

/** The shared rule, computed here so the client predicate is checked, not echoed. */
function expectedVisibleIds(all, query) {
  const normalised = String(query).trim().toLowerCase();
  return all
    .filter((recipe) => normalised === '' || searchableText(recipe).includes(normalised))
    .map((recipe) => recipe.id);
}

test('the client predicate agrees with the shared rule for every shared query', () => {
  const all = recipes();

  for (const query of SHARED_QUERIES) {
    const visible = all
      .filter((recipe) => matchesRecipe(searchableText(recipe), query))
      .map((recipe) => recipe.id);
    assert.deepEqual(
      visible,
      expectedVisibleIds(all, query),
      `for q=${JSON.stringify(query)} the client predicate leaves the wrong recipes visible`,
    );
  }
});

test('the shared list covers mixed case, padding and the zero-result path', () => {
  const all = recipes();

  assert.ok(
    SHARED_QUERIES.some(
      (query) => query !== query.toLowerCase() && query !== query.toUpperCase(),
    ),
    'the shared list must include a mixed-case query',
  );
  assert.ok(
    SHARED_QUERIES.some((query) => query !== query.trim()),
    'the shared list must include a whitespace-padded query',
  );
  assert.ok(
    SHARED_QUERIES.some((query) => expectedVisibleIds(all, query).length === 0),
    'the shared list must include a query that leaves no recipe visible',
  );
});

test('every searchable field is reachable by one shared query alone', () => {
  const all = recipes();

  for (const field of SEARCHABLE_FIELDS) {
    const fieldText = (recipe, name) => {
      const value = recipe[name];
      return (Array.isArray(value) ? value.map(String).join(' ') : String(value)).toLowerCase();
    };
    const covered = SHARED_QUERIES.some((query) => {
      const normalised = normaliseQuery(query);
      if (normalised === '') {
        return false;
      }
      return all.some((recipe) => {
        const others = SEARCHABLE_FIELDS.filter((name) => name !== field)
          .map((name) => fieldText(recipe, name))
          .join(' ');
        return fieldText(recipe, field).includes(normalised) && !others.includes(normalised);
      });
    });
    assert.ok(covered, `the shared list must reach the ${field} field alone`);
  }
});
