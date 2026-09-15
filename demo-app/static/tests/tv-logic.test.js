// Focus-transition tests for the pure TV model in static/tv-logic.js.
//
// Table-driven and offline: all four arrows, first/last-card clamping, vertical
// moves into a shorter rail and into an empty rail, and unhandled keys on the
// browse rails, plus the detail action model - both arrows with clamping at each
// end, Enter, the Escape/Backspace equivalence and unhandled keys.

import test from 'node:test';
import assert from 'node:assert/strict';

import {clampIndex, nextFocus, resolveDetailKey} from '../tv-logic.js';

const RAILS = [4, 2, 3, 0];

// The rendered TV detail action list: the back action, then My Cookbook.
const BACK = 0;
const COOKBOOK = 1;
const ACTIONS = 2;

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

test('resolveDetailKey moves between the two ordered actions', () => {
  assert.deepEqual(resolveDetailKey('ArrowDown', BACK, ACTIONS), {
    focusIndex: COOKBOOK,
    action: 'none',
  });
  assert.deepEqual(resolveDetailKey('ArrowUp', COOKBOOK, ACTIONS), {
    focusIndex: BACK,
    action: 'none',
  });
});

test('resolveDetailKey clamps at each end of the action list', () => {
  assert.deepEqual(
    resolveDetailKey('ArrowUp', BACK, ACTIONS),
    {focusIndex: BACK, action: 'none'},
    'there is no action above the back action',
  );
  assert.deepEqual(
    resolveDetailKey('ArrowDown', COOKBOOK, ACTIONS),
    {focusIndex: COOKBOOK, action: 'none'},
    'there is no action below My Cookbook',
  );

  // A held remote key settles on an end instead of addressing a missing action.
  let index = BACK;
  for (let press = 0; press < 5; press += 1) {
    index = resolveDetailKey('ArrowDown', index, ACTIONS).focusIndex;
  }
  assert.equal(index, COOKBOOK);
  for (let press = 0; press < 5; press += 1) {
    index = resolveDetailKey('ArrowUp', index, ACTIONS).focusIndex;
  }
  assert.equal(index, BACK);
});

test('resolveDetailKey yields activate for Enter without moving focus', () => {
  for (const focusIndex of [BACK, COOKBOOK]) {
    assert.deepEqual(resolveDetailKey('Enter', focusIndex, ACTIONS), {
      focusIndex,
      action: 'activate',
    });
  }
});

test('resolveDetailKey treats Escape and Backspace as the same back action', () => {
  for (const focusIndex of [BACK, COOKBOOK]) {
    const escape = resolveDetailKey('Escape', focusIndex, ACTIONS);
    const backspace = resolveDetailKey('Backspace', focusIndex, ACTIONS);
    assert.deepEqual(escape, {focusIndex, action: 'back'});
    assert.deepEqual(
      backspace,
      escape,
      'remotes send either key for the same physical button',
    );
  }
});

test('resolveDetailKey ignores every unhandled key', () => {
  const unhandled = [
    'ArrowLeft',
    'ArrowRight',
    'Tab',
    ' ',
    'Home',
    'MediaPlayPause',
    'enter',
    'escape',
    'backspace',
    '',
  ];
  for (const key of unhandled) {
    assert.deepEqual(
      resolveDetailKey(key, COOKBOOK, ACTIONS),
      {focusIndex: COOKBOOK, action: 'none'},
      `${key === '' ? '(empty key name)' : key} must not act on the detail page`,
    );
  }
});
