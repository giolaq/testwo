// Focus-transition tests for the pure TV model in static/tv-logic.js.
//
// Table-driven and offline: all four arrows, first/last-card clamping, vertical
// moves into a shorter rail and into an empty rail, and unhandled keys.

import test from 'node:test';
import assert from 'node:assert/strict';

import {clampIndex, nextFocus} from '../tv-logic.js';

const RAILS = [4, 2, 3, 0];

const CASES = [
  // ArrowRight within a rail, and clamped on the last card.
  {from: [0, 0], key: 'ArrowRight', to: [0, 1], why: 'next card in the rail'},
  {from: [0, 3], key: 'ArrowRight', to: [0, 3], why: 'clamps on the last card'},
  {from: [1, 1], key: 'ArrowRight', to: [1, 1], why: 'clamps in a two-card rail'},
  // ArrowLeft within a rail, and clamped on the first card.
  {from: [0, 2], key: 'ArrowLeft', to: [0, 1], why: 'previous card in the rail'},
  {from: [0, 0], key: 'ArrowLeft', to: [0, 0], why: 'clamps on the first card'},
  // ArrowDown / ArrowUp keeping the card position when it exists.
  {from: [0, 1], key: 'ArrowDown', to: [1, 1], why: 'keeps the card position'},
  {from: [2, 1], key: 'ArrowUp', to: [1, 1], why: 'keeps the card position'},
  // A vertical move into a shorter rail clamps to its last card.
  {from: [0, 3], key: 'ArrowDown', to: [1, 1], why: 'clamps into a shorter rail'},
  {from: [2, 2], key: 'ArrowUp', to: [1, 1], why: 'clamps into a shorter rail'},
  // Rail edges hold, and an empty destination rail leaves focus alone.
  {from: [0, 2], key: 'ArrowUp', to: [0, 2], why: 'no rail above the first'},
  {from: [2, 0], key: 'ArrowDown', to: [2, 0], why: 'the rail below is empty'},
  // Unhandled keys change nothing.
  {from: [1, 0], key: 'Enter', to: [1, 0], why: 'Enter is not a focus move'},
  {from: [1, 0], key: 'Escape', to: [1, 0], why: 'Escape is not a focus move'},
  {from: [1, 0], key: 'ArrowRightish', to: [1, 0], why: 'unknown keys are ignored'},
];

test('clampIndex clamps to the rail bounds', () => {
  assert.equal(clampIndex(1, 3), 1);
  assert.equal(clampIndex(-4, 3), 0);
  assert.equal(clampIndex(7, 3), 2);
  assert.equal(clampIndex(1, 0), 0, 'an empty rail has no addressable card');
});

test('nextFocus resolves every arrow and unhandled key', () => {
  for (const {from, key, to, why} of CASES) {
    const result = nextFocus({railIndex: from[0], cardIndex: from[1]}, RAILS, key);
    assert.deepEqual(
      [result.railIndex, result.cardIndex],
      to,
      `${key} from rail ${from[0]} card ${from[1]}: ${why}`,
    );
  }
});

test('nextFocus never mutates its input state', () => {
  const current = {railIndex: 0, cardIndex: 0};
  nextFocus(current, RAILS, 'ArrowDown');
  assert.deepEqual(current, {railIndex: 0, cardIndex: 0});
});

test('a walkthrough across two rails ends on an existing card', () => {
  let state = {railIndex: 0, cardIndex: 0};
  for (const key of ['ArrowRight', 'ArrowRight', 'ArrowDown', 'ArrowDown']) {
    state = nextFocus(state, RAILS, key);
  }
  assert.deepEqual([state.railIndex, state.cardIndex], [2, 1]);
  assert.ok(RAILS[state.railIndex] > state.cardIndex, 'the card exists in its rail');
});
