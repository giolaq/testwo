// Focus-transition tests for the pure TV model in static/tv-logic.js, plus the
// behaviour of the thin TV detail binding in static/tv-detail.js.
//
// Table-driven and offline: all four arrows, first/last-card clamping, vertical
// moves into a shorter rail and into an empty rail, and unhandled keys on the
// browse rails, plus the detail action model - both arrows with clamping at each
// end, Enter, the Escape/Backspace equivalence and unhandled keys.
//
// The binding cases run against a minimal element stub mirroring the markup of
// templates/tv_recipe.html, with the navigation and fetch seams injected, in the
// style of tests/browse-dom.test.js. No DOM, no network, no real navigation.

import test from 'node:test';
import assert from 'node:assert/strict';

import {clampIndex, nextFocus, resolveDetailKey} from '../tv-logic.js';
import {initTvDetail} from '../tv-detail.js';
import {initCookbookControls} from '../browse.js';
import {saveControlState} from '../browse-logic.js';

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

// ---------------------------------------------------------------------------
// The TV detail DOM binding (static/tv-detail.js)
// ---------------------------------------------------------------------------

const BACK_HREF = '/?mode=tv';
const RECIPE = {id: 'golden-oat-porridge', title: 'Golden Oat Porridge'};

/** Elements focused so far, in order, for the page currently under test. */
let focusLog = [];

/** A minimal element: only what tv-detail.js and browse.js read and write. */
class El {
  constructor(tag, attributes = {}, text = '') {
    this.tagName = tag.toUpperCase();
    this.parent = null;
    this.children = [];
    this.own = text;
    this.attributes = new Map(Object.entries(attributes).map(([k, v]) => [k, String(v)]));
    this.listeners = new Map();
  }

  append(...nodes) {
    for (const node of nodes) {
      node.parent = this;
      this.children.push(node);
    }
    return this;
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  get textContent() {
    return this.own + this.children.map((child) => child.textContent).join('');
  }

  set textContent(value) {
    this.children = [];
    this.own = String(value);
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  contains(node) {
    return node === this || this.descendants().includes(node);
  }

  // Supports only the selector forms these two modules use: '.class', '[attr]',
  // 'tag', 'tag[attr]' and comma-separated lists of those.
  matchesOne(selector) {
    if (selector.startsWith('.')) {
      return (this.getAttribute('class') || '').split(/\s+/).includes(selector.slice(1));
    }
    if (selector.startsWith('[')) {
      return this.hasAttribute(selector.slice(1, -1));
    }
    const parsed = /^([a-z]+)(?:\[([a-z-]+)\])?$/.exec(selector);
    if (!parsed) {
      return false;
    }
    const [, tag, attribute] = parsed;
    return this.tagName === tag.toUpperCase() && (!attribute || this.hasAttribute(attribute));
  }

  matches(selector) {
    return selector
      .split(',')
      .map((part) => part.trim())
      .some((part) => this.matchesOne(part));
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => node.matches(selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(handler);
  }

  focus() {
    focusLog.push(this);
    dispatch(this, 'focusin');
  }

  click() {
    dispatch(this, 'click');
  }
}

/** Dispatch an event that bubbles from `target` to the root, as a browser does. */
function dispatch(target, type, extra = {}) {
  let prevented = false;
  const event = {
    ...extra,
    type,
    target,
    preventDefault() {
      prevented = true;
    },
  };
  for (let node = target; node; node = node.parent) {
    for (const handler of node.listeners.get(type) || []) {
      handler.call(node, event);
    }
  }
  return {prevented};
}

const press = (target, key) => dispatch(target, 'keydown', {key});

/** The rendered TV detail page: a focusable brand link plus the action list. */
function tvDetailPage({saved = false} = {}) {
  focusLog = [];
  const root = new El('body');
  const brand = new El('a', {class: 'brand', href: BACK_HREF}, 'TableStory home');
  const back = new El('a', {class: 'tv-action', href: BACK_HREF}, 'Back to browse');
  const state = saveControlState(RECIPE.title, saved);
  const control = new El('button', {
    class: 'save-control',
    type: 'button',
    'data-recipe-id': RECIPE.id,
    'aria-pressed': String(state.pressed),
    'aria-label': state.label,
  }).append(
    new El('span', {class: 'save-control-mark'}, state.cue),
    new El('span', {class: 'save-control-text'}, state.text),
  );
  const list = new El('ol', {class: 'tv-actions', 'data-tv-actions': ''}).append(
    new El('li', {class: 'tv-action-item'}).append(back),
    new El('li', {class: 'tv-action-item'}).append(control),
  );
  root.append(
    new El('header', {class: 'topbar'}).append(brand),
    new El('main', {class: 'recipe-shell'}).append(list),
  );
  return {root, brand, back, control};
}

const tabindexes = (page) => [page.back.getAttribute('tabindex'), page.control.getAttribute('tabindex')];

function fetchStub(reply = () => ({ok: true, status: 201})) {
  const calls = [];
  const impl = (url, options = {}) => {
    calls.push({url: String(url), method: String(options.method || 'GET').toUpperCase()});
    return Promise.resolve(reply(calls.length));
  };
  return {impl, calls};
}

/** Let an awaited cookbook request settle without relying on real timers. */
async function settle() {
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
}

/** Run `body` with globalThis.location replaced by a recording navigation seam. */
async function withNavigationSeam(body) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'location');
  const hrefs = [];
  globalThis.location = {assign: (href) => hrefs.push(String(href))};
  try {
    return await body(hrefs);
  } finally {
    if (previous) {
      Object.defineProperty(globalThis, 'location', previous);
    } else {
      delete globalThis.location;
    }
  }
}

test('the binding focuses the back action first and marks it the only tab stop', () => {
  const page = tvDetailPage();
  initTvDetail(page.root);

  assert.deepEqual(tabindexes(page), ['0', '-1']);
  assert.equal(focusLog.at(-1), page.back, 'the remote must land on a real action');
});

test('ArrowDown and ArrowUp move focus and the tab stop across both actions', () => {
  const page = tvDetailPage();
  initTvDetail(page.root);

  press(page.back, 'ArrowDown');
  assert.deepEqual(tabindexes(page), ['-1', '0']);
  assert.equal(focusLog.at(-1), page.control);

  press(page.control, 'ArrowUp');
  assert.deepEqual(tabindexes(page), ['0', '-1']);
  assert.equal(focusLog.at(-1), page.back);

  // Clamping: a held key at either end keeps focus on an existing action.
  press(page.back, 'ArrowUp');
  assert.deepEqual(tabindexes(page), ['0', '-1']);
  assert.equal(focusLog.at(-1), page.back);
});

test('Escape and Backspace each follow the server-rendered back href exactly once', async () => {
  for (const key of ['Escape', 'Backspace']) {
    await withNavigationSeam(async (hrefs) => {
      const page = tvDetailPage();
      initTvDetail(page.root);

      press(page.control, key);

      assert.deepEqual(hrefs, [BACK_HREF], `${key} must return to TV browse once`);
    });
  }
});

test('Enter on the back action follows its own href', async () => {
  await withNavigationSeam(async (hrefs) => {
    const page = tvDetailPage();
    initTvDetail(page.root);

    press(page.back, 'Enter');

    assert.deepEqual(hrefs, [BACK_HREF]);
  });
});

test('Enter on the My Cookbook action toggles it exactly once through the shared binding', async () => {
  const page = tvDetailPage();
  const stub = fetchStub();

  await withNavigationSeam(async (hrefs) => {
    // browse.js binds the document in its own module body on a real page; here
    // the same shared binding is applied to the stub root, once.
    initCookbookControls(page.root, stub.impl);
    initTvDetail(page.root);

    press(page.control, 'Enter');
    await settle();

    const expected = saveControlState(RECIPE.title, true);
    assert.deepEqual(
      stub.calls,
      [{url: '/api/cookbook', method: 'POST'}],
      'one Enter must produce exactly one cookbook request',
    );
    assert.equal(page.control.getAttribute('aria-pressed'), 'true');
    assert.equal(page.control.getAttribute('aria-label'), expected.label);
    assert.equal(page.control.querySelector('.save-control-text').textContent, expected.text);
    assert.deepEqual(hrefs, [], 'activating the save control must not navigate');
  });
});

test('a pointer click on the My Cookbook action toggles it once, like Enter', async () => {
  const page = tvDetailPage();
  const stub = fetchStub();

  initCookbookControls(page.root, stub.impl);
  initTvDetail(page.root);

  page.control.click();
  await settle();

  assert.deepEqual(stub.calls, [{url: '/api/cookbook', method: 'POST'}]);
  assert.equal(page.control.getAttribute('aria-pressed'), 'true');
});

test('the binding owns no cookbook state of its own', async () => {
  const page = tvDetailPage();
  const stub = fetchStub();

  // Deliberately without the shared binding: initTvDetail must not stand in for
  // it, because a second state machine on the same control is what makes the two
  // disagree about what is saved.
  initTvDetail(page.root);
  press(page.control, 'Enter');
  await settle();

  assert.deepEqual(stub.calls, []);
  assert.equal(page.control.getAttribute('aria-pressed'), 'false');
});

test('Enter outside the action list leaves the browser to activate what has focus', async () => {
  const page = tvDetailPage();
  const stub = fetchStub();

  await withNavigationSeam(async (hrefs) => {
    initCookbookControls(page.root, stub.impl);
    initTvDetail(page.root);

    // Focus moved off the action list - the brand link is focusable too.
    dispatch(page.brand, 'focusin');
    const {prevented} = press(page.brand, 'Enter');
    await settle();

    assert.equal(prevented, false, 'the brand link must perform its own activation');
    assert.deepEqual(hrefs, [], 'the binding must not navigate on its behalf');
    assert.deepEqual(stub.calls, [], 'Enter on a link must never toggle My Cookbook');
    assert.equal(page.control.getAttribute('aria-pressed'), 'false');
  });
});

test('a stray remote key neither moves focus nor navigates', async () => {
  const page = tvDetailPage();
  const stub = fetchStub();

  await withNavigationSeam(async (hrefs) => {
    initCookbookControls(page.root, stub.impl);
    initTvDetail(page.root);
    const focusedBefore = focusLog.length;

    for (const key of ['Tab', ' ', 'ArrowLeft', 'MediaPlayPause', 'escape', '']) {
      press(page.back, key);
    }
    await settle();

    assert.equal(focusLog.length, focusedBefore, 'no stray key may move focus');
    assert.deepEqual(tabindexes(page), ['0', '-1']);
    assert.deepEqual(hrefs, []);
    assert.deepEqual(stub.calls, []);
  });
});
