// Acceptance tests for ticket #8: the TV recipe detail action model.
//
// Scope is FN_TV_DETAIL_KEY (resolveDetailKey in static/tv-logic.js) and the
// contract the TV detail binding (static/tv-detail.js) must honour:
//
//   * ArrowUp / ArrowDown move focus between the two actions and clamp at both
//     ends, so a held remote key never addresses a missing action
//   * Enter yields 'activate' with the focus index unchanged
//   * Escape and Backspace both yield 'back' and are indistinguishable
//   * every other key yields 'none' with the focus index unchanged, so stray
//     remote keys neither move focus nor navigate
//   * the model is pure and total: repeated calls agree and no input throws
//   * the DOM binding delegates key decisions to the pure model, reuses the
//     shared save helpers, and returns without binding when no action list is
//     rendered
//
// Runs offline under node --test with no DOM and no network. The modules are
// imported lazily inside the tests so a missing export or a missing file fails
// as a behaviour assertion rather than as an uncollectable module.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const TV_LOGIC_URL = new URL('../tv-logic.js', import.meta.url);
const TV_DETAIL_URL = new URL('../tv-detail.js', import.meta.url);

const BACK_INDEX = 0;
const COOKBOOK_INDEX = 1;
const ACTION_COUNT = 2;

async function loadExport(url, name, description) {
  const path = fileURLToPath(url);
  assert.ok(existsSync(path), `ticket #8 must add ${path} (${description})`);
  const module = await import(url.href);
  assert.equal(
    typeof module[name],
    'function',
    `${path} must export ${name}() — ${description}`,
  );
  return module[name];
}

const detailKey = () =>
  loadExport(
    TV_LOGIC_URL,
    'resolveDetailKey',
    'the pure TV detail action model resolveDetailKey(key, focusIndex, actionCount)',
  );

function readSource(url, description) {
  const path = fileURLToPath(url);
  assert.ok(existsSync(path), `ticket #8 must add ${path} (${description})`);
  return readFileSync(path, 'utf8');
}

// The approved signature is resolveDetailKey(key, focusIndex, actionCount);
// the helper keeps the (focusIndex, actionCount, key) reading order used by the
// table-driven cases below.
function callModel(resolve, focusIndex, actionCount, key) {
  return resolve(key, focusIndex, actionCount);
}

function expectIntent(resolve, focusIndex, actionCount, key, expected, note) {
  const intent = callModel(resolve, focusIndex, actionCount, key);
  assert.deepEqual(
    {focusIndex: intent && intent.focusIndex, action: intent && intent.action},
    expected,
    `${key} at focus ${focusIndex} of ${actionCount} action(s) must yield ` +
      `${JSON.stringify(expected)}${note ? ` — ${note}` : ''}; got ` +
      `${JSON.stringify(intent)}`,
  );
  return intent;
}

// --------------------------------------------------------------------------
// Vertical movement between the two actions
// --------------------------------------------------------------------------
test('ArrowDown moves from the back action to the My Cookbook action', async () => {
  const resolve = await detailKey();
  expectIntent(resolve, BACK_INDEX, ACTION_COUNT, 'ArrowDown', {
    focusIndex: COOKBOOK_INDEX,
    action: 'none',
  }, 'moving focus is not an activation');
});

test('ArrowUp moves from the My Cookbook action back to the back action', async () => {
  const resolve = await detailKey();
  expectIntent(resolve, COOKBOOK_INDEX, ACTION_COUNT, 'ArrowUp', {
    focusIndex: BACK_INDEX,
    action: 'none',
  });
});

test('ArrowUp on the first action clamps instead of wrapping or leaving the list', async () => {
  const resolve = await detailKey();
  expectIntent(resolve, BACK_INDEX, ACTION_COUNT, 'ArrowUp', {
    focusIndex: BACK_INDEX,
    action: 'none',
  }, 'a held remote key must not address a missing action');
});

test('ArrowDown on the last action clamps instead of wrapping', async () => {
  const resolve = await detailKey();
  expectIntent(resolve, COOKBOOK_INDEX, ACTION_COUNT, 'ArrowDown', {
    focusIndex: COOKBOOK_INDEX,
    action: 'none',
  });
});

test('repeated ArrowDown presses settle on the last action', async () => {
  const resolve = await detailKey();
  let focusIndex = BACK_INDEX;
  for (let press = 0; press < 5; press += 1) {
    focusIndex = callModel(resolve, focusIndex, ACTION_COUNT, 'ArrowDown').focusIndex;
  }
  assert.equal(focusIndex, COOKBOOK_INDEX);
});

test('repeated ArrowUp presses settle on the first action', async () => {
  const resolve = await detailKey();
  let focusIndex = COOKBOOK_INDEX;
  for (let press = 0; press < 5; press += 1) {
    focusIndex = callModel(resolve, focusIndex, ACTION_COUNT, 'ArrowUp').focusIndex;
  }
  assert.equal(focusIndex, BACK_INDEX);
});

test('an out-of-range focus index is clamped into the rendered action list', async () => {
  const resolve = await detailKey();
  for (const key of ['ArrowUp', 'ArrowDown', 'Enter', 'Escape']) {
    for (const focusIndex of [-3, -1, ACTION_COUNT, ACTION_COUNT + 4]) {
      const intent = callModel(resolve, focusIndex, ACTION_COUNT, key);
      assert.ok(
        intent.focusIndex >= 0 && intent.focusIndex < ACTION_COUNT,
        `${key} from an out-of-range focus index ${focusIndex} must resolve to ` +
          `an existing action, got ${intent.focusIndex}`,
      );
    }
  }
});

test('a single rendered action leaves focus on index 0 for both arrows', async () => {
  const resolve = await detailKey();
  for (const key of ['ArrowUp', 'ArrowDown']) {
    expectIntent(resolve, 0, 1, key, {focusIndex: 0, action: 'none'});
  }
});

test('horizontal arrows do not move focus in the vertical action list', async () => {
  const resolve = await detailKey();
  for (const key of ['ArrowLeft', 'ArrowRight']) {
    for (const focusIndex of [BACK_INDEX, COOKBOOK_INDEX]) {
      expectIntent(resolve, focusIndex, ACTION_COUNT, key, {
        focusIndex,
        action: 'none',
      }, 'the TV actions are stacked vertically');
    }
  }
});

// --------------------------------------------------------------------------
// Activate
// --------------------------------------------------------------------------
test('Enter activates the focused action without moving focus', async () => {
  const resolve = await detailKey();
  for (const focusIndex of [BACK_INDEX, COOKBOOK_INDEX]) {
    expectIntent(resolve, focusIndex, ACTION_COUNT, 'Enter', {
      focusIndex,
      action: 'activate',
    });
  }
});

// --------------------------------------------------------------------------
// Back: Escape and Backspace are equivalent
// --------------------------------------------------------------------------
test('Escape yields the back intent from either action', async () => {
  const resolve = await detailKey();
  for (const focusIndex of [BACK_INDEX, COOKBOOK_INDEX]) {
    expectIntent(resolve, focusIndex, ACTION_COUNT, 'Escape', {
      focusIndex,
      action: 'back',
    }, 'Escape returns to TV browse regardless of which action holds focus');
  }
});

test('Backspace yields the back intent from either action', async () => {
  const resolve = await detailKey();
  for (const focusIndex of [BACK_INDEX, COOKBOOK_INDEX]) {
    expectIntent(resolve, focusIndex, ACTION_COUNT, 'Backspace', {
      focusIndex,
      action: 'back',
    });
  }
});

test('Escape and Backspace are indistinguishable', async () => {
  const resolve = await detailKey();
  for (const focusIndex of [BACK_INDEX, COOKBOOK_INDEX]) {
    assert.deepEqual(
      callModel(resolve, focusIndex, ACTION_COUNT, 'Escape'),
      callModel(resolve, focusIndex, ACTION_COUNT, 'Backspace'),
      'remotes send Escape or Backspace for the same physical back button, so ' +
        'the two keys must produce identical intents',
    );
  }
});

// --------------------------------------------------------------------------
// Unhandled keys
// --------------------------------------------------------------------------
test('unhandled keys neither move focus nor navigate', async () => {
  const resolve = await detailKey();
  const strayKeys = [
    'Tab',
    ' ',
    'Space',
    'a',
    'A',
    'Home',
    'End',
    'PageDown',
    'MediaPlayPause',
    'Unidentified',
    '',
    'arrowdown',
    'ENTER',
    'escape',
  ];
  for (const key of strayKeys) {
    for (const focusIndex of [BACK_INDEX, COOKBOOK_INDEX]) {
      expectIntent(resolve, focusIndex, ACTION_COUNT, key, {
        focusIndex,
        action: 'none',
      }, 'stray remote keys must never navigate away from the recipe');
    }
  }
});

test('key names are matched exactly, so lower-case variants never navigate', async () => {
  const resolve = await detailKey();
  for (const key of ['escape', 'backspace', 'enter']) {
    const intent = callModel(resolve, BACK_INDEX, ACTION_COUNT, key);
    assert.equal(
      intent.action,
      'none',
      `${key} is not a DOM key name and must not resolve to an action`,
    );
  }
});

// --------------------------------------------------------------------------
// Purity and totality
// --------------------------------------------------------------------------
test('the action model is pure: repeated calls agree', async () => {
  const resolve = await detailKey();
  for (const key of ['ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Backspace', 'x']) {
    const first = callModel(resolve, BACK_INDEX, ACTION_COUNT, key);
    const second = callModel(resolve, BACK_INDEX, ACTION_COUNT, key);
    assert.deepEqual(second, first, `${key} must be deterministic`);
  }
});

test('the action model always reports a known action and an integer focus index', async () => {
  const resolve = await detailKey();
  const keys = ['ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Backspace', 'Tab', ''];
  for (const key of keys) {
    for (const focusIndex of [-1, 0, 1, 7]) {
      const intent = callModel(resolve, focusIndex, ACTION_COUNT, key);
      assert.ok(
        intent && typeof intent === 'object',
        `${key} must resolve to an intent object`,
      );
      assert.ok(
        ['none', 'activate', 'back'].includes(intent.action),
        `${key} resolved to the unknown action ${JSON.stringify(intent.action)}`,
      );
      assert.equal(
        Number.isInteger(intent.focusIndex),
        true,
        `${key} must resolve to an integer focus index, got ` +
          `${JSON.stringify(intent.focusIndex)}`,
      );
    }
  }
});

// --------------------------------------------------------------------------
// The TV detail DOM binding
// --------------------------------------------------------------------------
test('the TV detail binding exports initTvDetail', async () => {
  await loadExport(
    TV_DETAIL_URL,
    'initTvDetail',
    'the TV detail DOM binding initTvDetail(root)',
  );
});

test('the TV detail binding delegates key decisions to the pure action model', () => {
  const source = readSource(TV_DETAIL_URL, 'the TV detail DOM binding');
  assert.match(
    source,
    /tv-logic\.js/,
    'tv-detail.js must import the pure action model from ./tv-logic.js instead ' +
      'of deciding key handling in the DOM layer',
  );
  assert.match(
    source,
    /resolveDetailKey/,
    'tv-detail.js must route each key through resolveDetailKey',
  );
});

test('the TV detail binding reuses the shared save-control helpers', () => {
  const source = readSource(TV_DETAIL_URL, 'the TV detail DOM binding');
  assert.match(
    source,
    /saveControlState|requestCookbookChange|initCookbookControls|browse(-logic)?\.js/,
    'the TV My Cookbook action must reuse the shared save label and cookbook ' +
      'request helpers so it cannot drift from the mobile control',
  );
});

test('the TV detail binding uses the server-rendered back href', () => {
  const source = readSource(TV_DETAIL_URL, 'the TV detail DOM binding');
  assert.doesNotMatch(
    source,
    /mode=tv/,
    'the back intent must navigate to the href the server already rendered, ' +
      'so TV mode retention is not re-derived in JavaScript',
  );
});

test('initTvDetail returns without binding when no TV action list is rendered', async () => {
  const initTvDetail = await loadExport(
    TV_DETAIL_URL,
    'initTvDetail',
    'the TV detail DOM binding initTvDetail(root)',
  );
  const listeners = [];
  const emptyRoot = {
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    addEventListener: (type) => listeners.push(type),
  };
  assert.doesNotThrow(
    () => initTvDetail(emptyRoot),
    'initTvDetail must return quietly when the TV action list is absent',
  );
  assert.deepEqual(
    listeners,
    [],
    'initTvDetail must not bind key handling when there is no action list to ' +
      `move focus between; it registered ${JSON.stringify(listeners)}`,
  );
});
