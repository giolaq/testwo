// Acceptance tests for ticket #9: the shared search-parity query list asserted
// client-side.
//
// Scope is the client half of C_SEARCH_JS / FN_TEST_PARITY: the one shared
// sample-query list that demo-app/tests/test_parity.py runs through
// GET /api/recipes?q=... must also be asserted by the node browse-logic suite
// against matchesRecipe(), so the Python and JavaScript predicates cannot drift.
//
//   * the shared list is discoverable in demo-app/tests/test_parity.py and holds
//     at least six queries
//   * every shared query also appears in the node suite, so both runners assert
//     the same list rather than two lists that can diverge
//   * for every shared query, matchesRecipe() over each recipe's five-field
//     searchable text agrees with the shared normalisation and containment rule
//     computed independently here from demo-app/recipes.json
//   * normaliseQuery() trims and case-folds, and a non-string means
//     "match everything"
//   * the list contains at least one query that leaves no recipe visible
//
// Runs offline under node --test with no DOM and no network. Sources are read
// and modules imported lazily inside the tests, so a missing file fails as a
// behaviour assertion rather than as an uncollectable module.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync, readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const BROWSE_LOGIC_URL = new URL('../browse-logic.js', import.meta.url);
const PARITY_TEST_URL = new URL('../../tests/test_parity.py', import.meta.url);
const RECIPES_URL = new URL('../../recipes.json', import.meta.url);
const TESTS_DIR_URL = new URL('./', import.meta.url);

const SELF = 'ticket-9-search-parity-queries.test.js';

// The five searchable fields, in the order demo-app/recipe_search.py folds them.
const SEARCHABLE_FIELDS = [
  'title',
  'description',
  'category',
  'dietary_tags',
  'ingredients',
];

function readSource(url, description) {
  const path = fileURLToPath(url);
  assert.ok(existsSync(path), `ticket #9 must add ${path} (${description})`);
  return readFileSync(path, 'utf8');
}

/** Strip triple-quoted blocks and comments so only code literals are scanned. */
function pythonCode(source) {
  return source
    .replace(/"""[\s\S]*?"""/g, '""')
    .replace(/'''[\s\S]*?'''/g, "''")
    .split('\n')
    .filter((line) => !line.trimStart().startsWith('#'))
    .join('\n');
}

function stringLiterals(text) {
  const literals = [];
  const pattern = /(['"])((?:\\.|(?!\1)[^\\\n])*)\1/g;
  let match = pattern.exec(text);
  while (match !== null) {
    literals.push(
      match[2]
        .replace(/\\n/g, '\n')
        .replace(/\\t/g, '\t')
        .replace(/\\(['"\\])/g, '$1'),
    );
    match = pattern.exec(text);
  }
  return literals;
}

/** Balanced bracket spans of the Python source, longest-literal span first. */
function bracketSpans(code) {
  const spans = [];
  const openers = {'[': ']', '(': ')'};
  for (let start = 0; start < code.length; start += 1) {
    const closer = openers[code[start]];
    if (closer === undefined) {
      continue;
    }
    let depth = 0;
    let quote = null;
    for (let at = start; at < code.length; at += 1) {
      const char = code[at];
      if (quote !== null) {
        if (char === '\\') {
          at += 1;
        } else if (char === quote) {
          quote = null;
        }
        continue;
      }
      if (char === '"' || char === "'") {
        quote = char;
        continue;
      }
      if (char === '[' || char === '(') {
        depth += 1;
      } else if (char === ']' || char === ')') {
        depth -= 1;
        if (depth === 0) {
          spans.push(code.slice(start, at + 1));
          break;
        }
      }
    }
  }
  return spans;
}

/**
 * The shared sample-query list from demo-app/tests/test_parity.py.
 *
 * The queries are short single-line strings and never paths, which is what
 * separates the shared list from message or path literals elsewhere in the file.
 */
function sharedQueries() {
  const code = pythonCode(
    readSource(PARITY_TEST_URL, 'the server/client search parity test'),
  );
  const candidates = bracketSpans(code)
    .map((span) => stringLiterals(span))
    .filter(
      (literals) =>
        literals.length >= 6 &&
        literals.every(
          (literal) =>
            literal.length > 0 &&
            literal.length <= 40 &&
            !literal.includes('\n') &&
            !literal.includes('/'),
        ),
    )
    .sort((left, right) => right.length - left.length);

  assert.ok(
    candidates.length > 0,
    `${fileURLToPath(PARITY_TEST_URL)} must expose one shared sample-query list ` +
      '(mixed case, whitespace padded, one query per searchable field, one ' +
      'non-matching query) that both suites assert',
  );
  return candidates[0];
}

function nodeSuiteSources() {
  const dir = fileURLToPath(TESTS_DIR_URL);
  return readdirSync(dir)
    .filter((name) => name.endsWith('.test.js') && name !== SELF)
    .map((name) => readFileSync(new URL(name, TESTS_DIR_URL), 'utf8'))
    .join('\n');
}

function recipes() {
  return JSON.parse(readSource(RECIPES_URL, 'the recipe collection'));
}

/** The shared rule, implemented here so the client predicate is checked, not echoed. */
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

function expectedVisibleIds(all, query) {
  const normalised = String(query).trim().toLowerCase();
  return all
    .filter((recipe) => normalised === '' || searchableText(recipe).includes(normalised))
    .map((recipe) => recipe.id);
}

async function browseLogic() {
  const path = fileURLToPath(BROWSE_LOGIC_URL);
  assert.ok(existsSync(path), `${path} must exist for the client search predicate`);
  const module = await import(BROWSE_LOGIC_URL.href);
  for (const name of ['matchesRecipe', 'normaliseQuery']) {
    assert.equal(
      typeof module[name],
      'function',
      `${path} must export ${name}() so the shared queries can be asserted`,
    );
  }
  return module;
}

test('the shared parity query list is asserted by the node suite too', () => {
  const queries = sharedQueries();
  const suite = nodeSuiteSources();

  for (const query of queries) {
    assert.ok(
      suite.includes(query),
      `the node browse-logic suite must assert the shared query ${JSON.stringify(query)} ` +
        'so the Python and JavaScript predicates cannot drift',
    );
  }
});

test('the client predicate matches the shared rule for every shared query', async () => {
  const {matchesRecipe} = await browseLogic();
  const all = recipes();

  for (const query of sharedQueries()) {
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

test('the shared list includes a query that leaves no recipe visible', () => {
  const all = recipes();
  const empty = sharedQueries().filter(
    (query) => expectedVisibleIds(all, query).length === 0,
  );
  assert.ok(
    empty.length >= 1,
    'the shared list must include one non-matching query so the zero-result path ' +
      'is covered on both sides',
  );
});

test('the shared list includes a mixed-case and a whitespace-padded query', () => {
  const queries = sharedQueries();
  assert.ok(
    queries.some((query) => query !== query.toLowerCase() && query !== query.toUpperCase()),
    'the shared list must include a mixed-case query',
  );
  assert.ok(
    queries.some((query) => query !== query.trim()),
    'the shared list must include a whitespace-padded query',
  );
});

test('normaliseQuery trims, case-folds, and treats a non-string as empty', async () => {
  const {normaliseQuery, matchesRecipe} = await browseLogic();

  assert.equal(normaliseQuery('  Golden Oat  '), 'golden oat');
  assert.equal(normaliseQuery(undefined), '');
  assert.equal(normaliseQuery(null), '');
  assert.equal(matchesRecipe('anything at all', undefined), true);
});
