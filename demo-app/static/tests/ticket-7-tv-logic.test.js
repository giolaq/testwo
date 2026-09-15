// Acceptance tests for ticket #7: the pure TV focus model.
//
// Scope is demo-app/static/tv-logic.js (MOD_TV_LOGIC, C_TV_FOCUS) and only the
// two pure helpers this ticket owns: FN_TV_NEXT_FOCUS (nextFocus) and
// FN_TV_CLAMP (clampIndex). The TV detail action model (resolveDetailKey) lands
// in T-TVDETAIL and is deliberately not asserted here, so this file never
// freezes its absence.
//
// The module is imported lazily behind a file-existence assertion so a missing
// module fails as a behaviour assertion rather than as an unhandled module
// resolution error. Everything is offline, DOM-free and deterministic.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const MODULE_URL = new URL('../tv-logic.js', import.meta.url);

const ARROWS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];

async function tvLogic() {
  assert.ok(
    existsSync(fileURLToPath(MODULE_URL)),
    'ticket #7 must add demo-app/static/tv-logic.js with the pure TV focus model',
  );
  const module = await import(MODULE_URL.href);
  for (const name of ['nextFocus', 'clampIndex']) {
    assert.equal(
      typeof module[name],
      'function',
      `tv-logic.js must export ${name}()`,
    );
  }
  return module;
}

function state(railIndex, cardIndex) {
  return {railIndex, cardIndex};
}

function label(from, key, railCounts) {
  return `nextFocus({railIndex: ${from.railIndex}, cardIndex: ${from.cardIndex}}, [${railCounts}], '${key}')`;
}

async function expectFocus(from, key, railCounts, expected) {
  const {nextFocus} = await tvLogic();
  const result = nextFocus({...from}, [...railCounts], key);
  assert.deepEqual(
    {railIndex: result.railIndex, cardIndex: result.cardIndex},
    expected,
    `${label(from, key, railCounts)} must yield {railIndex: ${expected.railIndex}, cardIndex: ${expected.cardIndex}}`,
  );
}

// --------------------------------------------------------------------------- //
// clampIndex  (FN_TV_CLAMP)
// --------------------------------------------------------------------------- //
test('clampIndex keeps an index inside the rail', async () => {
  const {clampIndex} = await tvLogic();
  assert.equal(clampIndex(1, 3), 1);
  assert.equal(clampIndex(0, 3), 0);
  assert.equal(clampIndex(2, 3), 2);
});

test('clampIndex clamps below zero and past the last card', async () => {
  const {clampIndex} = await tvLogic();
  assert.equal(clampIndex(-1, 3), 0, 'an index below zero clamps to the first card');
  assert.equal(clampIndex(-9, 3), 0);
  assert.equal(clampIndex(3, 3), 2, 'an index past the end clamps to the last card');
  assert.equal(clampIndex(99, 4), 3);
});

test('clampIndex returns 0 for an empty rail', async () => {
  const {clampIndex} = await tvLogic();
  assert.equal(clampIndex(2, 0), 0);
});

// --------------------------------------------------------------------------- //
// Horizontal movement, clamped at both edges  (R32)
// --------------------------------------------------------------------------- //
test('ArrowRight moves to the next card in the same rail', async () => {
  await expectFocus(state(0, 0), 'ArrowRight', [3, 2, 4], state(0, 1));
  await expectFocus(state(1, 0), 'ArrowRight', [3, 2, 4], state(1, 1));
  await expectFocus(state(2, 1), 'ArrowRight', [3, 2, 4], state(2, 2));
});

test('ArrowLeft moves to the previous card in the same rail', async () => {
  await expectFocus(state(0, 2), 'ArrowLeft', [3, 2, 4], state(0, 1));
  await expectFocus(state(2, 3), 'ArrowLeft', [3, 2, 4], state(2, 2));
});

test('ArrowRight clamps on the last card without wrapping', async () => {
  await expectFocus(state(0, 2), 'ArrowRight', [3, 2, 4], state(0, 2));
  await expectFocus(state(1, 1), 'ArrowRight', [3, 2, 4], state(1, 1));
});

test('ArrowLeft clamps on the first card without wrapping', async () => {
  await expectFocus(state(0, 0), 'ArrowLeft', [3, 2, 4], state(0, 0));
  await expectFocus(state(2, 0), 'ArrowLeft', [3, 2, 4], state(2, 0));
});

test('a single-card rail keeps focus on its only card', async () => {
  await expectFocus(state(0, 0), 'ArrowRight', [1, 2], state(0, 0));
  await expectFocus(state(0, 0), 'ArrowLeft', [1, 2], state(0, 0));
});

// --------------------------------------------------------------------------- //
// Vertical movement between rails  (R32)
// --------------------------------------------------------------------------- //
test('ArrowDown moves to the next rail keeping the card position when it exists', async () => {
  await expectFocus(state(0, 1), 'ArrowDown', [3, 4, 2], state(1, 1));
  await expectFocus(state(1, 3), 'ArrowDown', [3, 4, 5], state(2, 3));
});

test('ArrowUp moves to the previous rail keeping the card position when it exists', async () => {
  await expectFocus(state(1, 2), 'ArrowUp', [4, 4, 2], state(0, 2));
  await expectFocus(state(2, 0), 'ArrowUp', [3, 4, 2], state(1, 0));
});

test('a vertical move into a shorter rail clamps to its last card', async () => {
  await expectFocus(state(0, 3), 'ArrowDown', [4, 2, 5], state(1, 1));
  await expectFocus(state(2, 4), 'ArrowUp', [4, 2, 5], state(1, 1));
});

test('ArrowUp on the first rail and ArrowDown on the last rail keep the state', async () => {
  await expectFocus(state(0, 1), 'ArrowUp', [3, 2, 4], state(0, 1));
  await expectFocus(state(2, 3), 'ArrowDown', [3, 2, 4], state(2, 3));
});

test('an empty destination rail leaves focus on the current rail', async () => {
  await expectFocus(state(0, 1), 'ArrowDown', [3, 0, 4], state(0, 1));
  await expectFocus(state(2, 2), 'ArrowUp', [3, 0, 4], state(2, 2));
});

// --------------------------------------------------------------------------- //
// Unhandled keys and totality  (C_TV_FOCUS)
// --------------------------------------------------------------------------- //
test('unhandled keys return the state unchanged', async () => {
  const railCounts = [3, 2, 4];
  for (const key of ['Enter', 'Escape', 'Backspace', 'Tab', 'a', 'arrowright', '']) {
    await expectFocus(state(1, 1), key, railCounts, state(1, 1));
  }
});

test('nextFocus does not mutate the state it is given', async () => {
  const {nextFocus} = await tvLogic();
  const current = state(0, 0);
  nextFocus(current, [3, 2], 'ArrowRight');
  assert.deepEqual(
    current,
    {railIndex: 0, cardIndex: 0},
    'nextFocus must be pure and return a new state rather than mutating its input',
  );
});

test('every returned state addresses an existing card', async () => {
  const {nextFocus} = await tvLogic();
  const layouts = [
    [3, 2, 4, 0],
    [4, 4, 2, 1],
    [1, 5, 0, 3],
    [2, 2],
  ];

  for (const railCounts of layouts) {
    for (let railIndex = 0; railIndex < railCounts.length; railIndex += 1) {
      if (railCounts[railIndex] === 0) {
        continue;
      }
      for (let cardIndex = 0; cardIndex < railCounts[railIndex]; cardIndex += 1) {
        for (const key of ARROWS) {
          const result = nextFocus({railIndex, cardIndex}, [...railCounts], key);
          const where = `${label({railIndex, cardIndex}, key, railCounts)} -> {railIndex: ${result.railIndex}, cardIndex: ${result.cardIndex}}`;
          assert.ok(
            Number.isInteger(result.railIndex) && result.railIndex >= 0 && result.railIndex < railCounts.length,
            `${where} must address a rendered rail`,
          );
          assert.ok(
            railCounts[result.railIndex] > 0,
            `${where} must never land on an empty rail`,
          );
          assert.ok(
            Number.isInteger(result.cardIndex)
              && result.cardIndex >= 0
              && result.cardIndex < railCounts[result.railIndex],
            `${where} must address an existing card in that rail`,
          );
        }
      }
    }
  }
});

// --------------------------------------------------------------------------- //
// A keyboard-only walkthrough across two rails  (R32, FLOW_TV_BROWSE)
// --------------------------------------------------------------------------- //
test('an arrow-key walkthrough crosses two rails and ends on a real card', async () => {
  const {nextFocus} = await tvLogic();
  const railCounts = [4, 2, 3, 0];
  const keys = ['ArrowRight', 'ArrowRight', 'ArrowDown', 'ArrowRight', 'ArrowDown', 'ArrowLeft'];

  let current = state(0, 0);
  const visitedRails = new Set([current.railIndex]);
  for (const key of keys) {
    current = nextFocus(current, railCounts, key);
    visitedRails.add(current.railIndex);
  }

  assert.ok(
    visitedRails.size >= 3,
    `the walkthrough must move focus across at least two rails, visited ${[...visitedRails]}`,
  );
  assert.deepEqual(
    {railIndex: current.railIndex, cardIndex: current.cardIndex},
    state(2, 0),
    'the walkthrough must end on the first card of the third rail',
  );
});
