// Implementation-owned tests for the browse logic module. Added in the same
// change that deletes app-logic.test.js, so demo-app/static/tests never goes
// empty and `node --test demo-app/static/tests/*.test.js` always matches a file.
// Offline and deterministic: expectations come from the committed fixture.

import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

import {
  emptyStateVisible,
  matchCountLabel,
  matchesRecipe,
  nextCookbook,
  normaliseQuery,
  saveControlState,
  titleFromControlLabel,
} from '../browse-logic.js';

const FIXTURE_URL = new URL('../../recipes.json', import.meta.url);
const SEARCHABLE_FIELDS = ['title', 'description', 'category', 'dietary_tags', 'ingredients'];

const recipes = JSON.parse(readFileSync(fileURLToPath(FIXTURE_URL), 'utf8'));

// The shared parity sample queries: mixed case, whitespace padded, one query per
// searchable field and one that matches nothing. The Python side runs the same
// shapes through GET /api/recipes in demo-app/tests, so the two normalisations
// cannot drift without a red gate.
const PARITY_SAMPLE_QUERIES = [
  '',
  '   ',
  'Oat',
  '  VEGAN ',
  'dessert',
  'Breakfast',
  'lemon',
  'zzz-no-such-dish-zzz',
];

// The same expected strings the server helper cookbook_control_label() is
// asserted against in demo-app/tests/test_ticket_6_save_control_parity.py.
const SAVE_LABEL_CASES = [
  ['Golden Oat Porridge', false, 'Add Golden Oat Porridge to My Cookbook'],
  ['Golden Oat Porridge', true, 'Remove Golden Oat Porridge from My Cookbook'],
  ['Lemon Chickpea Salad', false, 'Add Lemon Chickpea Salad to My Cookbook'],
  ['Lemon Chickpea Salad', true, 'Remove Lemon Chickpea Salad from My Cookbook'],
  ['Tomato and Basil Toastie', false, 'Add Tomato and Basil Toastie to My Cookbook'],
  ['Tomato and Basil Toastie', true, 'Remove Tomato and Basil Toastie from My Cookbook'],
];

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
  const queries = [...PARITY_SAMPLE_QUERIES, 'Vegan', 'vegan', '  DESSERT ', 'no-such-thing'];
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

test('the parity sample queries fold identically to the server rule', () => {
  for (const query of PARITY_SAMPLE_QUERIES) {
    assert.equal(normaliseQuery(query), query.trim().toLowerCase());
  }
});

test('nextCookbook toggles membership and keeps insertion order', () => {
  const ids = recipes.slice(0, 3).map((recipe) => recipe.id);
  const [first, second, third] = ids;

  assert.deepEqual(nextCookbook([], first), [first]);
  assert.deepEqual(nextCookbook([first], second), [first, second]);
  assert.deepEqual(nextCookbook([first, second, third], second), [first, third]);
  assert.deepEqual(nextCookbook([first, second], first), [second]);
});

test('nextCookbook leaves its input untouched and degrades a non-list', () => {
  const current = ['golden-oat-porridge'];
  assert.notEqual(nextCookbook(current, 'honey-roast-plums'), current);
  assert.deepEqual(current, ['golden-oat-porridge']);
  assert.deepEqual(nextCookbook(undefined, 'honey-roast-plums'), ['honey-roast-plums']);
});

test('matchCountLabel pluralises in the recipe domain', () => {
  assert.equal(matchCountLabel(0), '0 recipes');
  assert.equal(matchCountLabel(1), '1 recipe');
  assert.equal(matchCountLabel(2), '2 recipes');
  assert.equal(matchCountLabel(recipes.length), `${recipes.length} recipes`);
});

test('emptyStateVisible is true only for a zero count', () => {
  assert.equal(emptyStateVisible(0), true);
  for (let count = 1; count <= recipes.length; count += 1) {
    assert.equal(emptyStateVisible(count), false);
  }
});

test('saveControlState labels equal the shared expected strings', () => {
  for (const [title, saved, label] of SAVE_LABEL_CASES) {
    const state = saveControlState(title, saved);
    assert.equal(state.label, label);
    assert.equal(state.pressed, saved);
  }
});

test('saveControlState carries a non-colour cue and visible text per state', () => {
  const unsaved = saveControlState('Golden Oat Porridge', false);
  const saved = saveControlState('Golden Oat Porridge', true);

  assert.notEqual(saved.cue, unsaved.cue);
  assert.notEqual(saved.text, unsaved.text);
  for (const state of [unsaved, saved]) {
    assert.notEqual(state.cue.trim(), '');
    assert.notEqual(state.text.trim(), '');
  }
});

test('titleFromControlLabel inverts every rendered label in the fixture', () => {
  for (const recipe of recipes) {
    for (const saved of [false, true]) {
      const {label} = saveControlState(recipe.title, saved);
      assert.equal(titleFromControlLabel(label), recipe.title);
    }
  }
});

test('titleFromControlLabel returns an empty title for foreign wording', () => {
  for (const value of ['', 'Save this dish', undefined, null, 42]) {
    assert.equal(titleFromControlLabel(value), '');
  }
});
