// Implementation-owned tests for the thin browse binding (demo-app/static/browse.js).
//
// The gate has no DOM and no network, so the binding runs against a minimal
// element stub that mirrors the markup the server renders
// (demo-app/templates/browse.html and _partials/{recipe_card,save_control}.html)
// and against an injected fetch stub. Nothing here touches the real fetch: the
// global is replaced with a throwing function while a case runs, so an accidental
// direct call fails loudly.

import test from 'node:test';
import assert from 'node:assert/strict';

import {initBrowseSearch, initCookbookControls, requestCookbookChange} from '../browse.js';
import {matchCountLabel, saveControlState} from '../browse-logic.js';

const EMPTY_STATE_TEXT = 'No recipes found. Try another ingredient or dish.';

// ---------------------------------------------------------------------------
// A minimal element stub: only what browse.js reads and writes.
// ---------------------------------------------------------------------------

class Node {
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

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  get hidden() {
    return this.hasAttribute('hidden');
  }

  set hidden(value) {
    if (value) this.setAttribute('hidden', '');
    else this.removeAttribute('hidden');
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

  // Supports only the selector forms browse.js uses: '#id' and '.class'.
  matches(selector) {
    if (selector.startsWith('#')) return this.getAttribute('id') === selector.slice(1);
    const classes = (this.getAttribute('class') || '').split(/\s+/);
    return classes.includes(selector.slice(1));
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => node.matches(selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  fire(type) {
    const event = {type, target: this, preventDefault() {}};
    for (const handler of this.listeners.get(type) || []) handler.call(this, event);
  }

  click() {
    this.fire('click');
  }
}

function saveControl(recipe, saved) {
  const state = saveControlState(recipe.title, saved);
  const control = new Node('button', {
    class: 'save-control',
    type: 'button',
    'data-recipe-id': recipe.id,
    'aria-pressed': String(state.pressed),
    'aria-label': state.label,
  });
  return control.append(
    new Node('span', {class: 'save-control-mark', 'aria-hidden': 'true'}, state.cue),
    new Node('span', {class: 'save-control-text'}, state.text),
  );
}

// Three deterministic cards; search text is what the server's searchable_text()
// would emit, folded, so no fixture read is needed for these cases.
const CARDS = [
  {id: 'golden-oat-porridge', title: 'Golden Oat Porridge', text: 'golden oat porridge breakfast vegetarian oats'},
  {id: 'lemon-chickpea-salad', title: 'Lemon Chickpea Salad', text: 'lemon chickpea salad lunch vegan chickpeas'},
  {id: 'honey-roast-plums', title: 'Honey Roast Plums', text: 'honey roast plums dessert vegetarian plums'},
];

function browsePage(savedIds = []) {
  const root = new Node('body');
  const search = new Node('input', {id: 'recipe-search', type: 'search', name: 'q'});
  search.value = '';
  const grid = new Node('section', {class: 'recipe-grid', id: 'recipe-grid'});
  const count = new Node('span', {id: 'count'}, matchCountLabel(CARDS.length));
  const emptyState = new Node('p', {class: 'empty-state', id: 'empty-state', hidden: ''}, EMPTY_STATE_TEXT);

  for (const card of CARDS) {
    const article = new Node('article', {
      class: 'recipe-card',
      'data-recipe-id': card.id,
      'data-search-text': card.text,
    });
    article.append(
      new Node('a', {class: 'recipe-card-link', href: `/recipe/${card.id}`}),
      saveControl(card, savedIds.includes(card.id)),
    );
    grid.append(article);
  }
  root.append(search, count, grid, emptyState);
  return {root, search, grid, count, emptyState};
}

/** The recipe page: one control, no search field and no card container. */
function detailPage(card, saved = false) {
  const root = new Node('body');
  const control = saveControl(card, saved);
  root.append(new Node('main', {class: 'recipe-shell'}).append(control));
  return {root, control};
}

function fetchStub(reply = () => ({ok: true, status: 201})) {
  const calls = [];
  const impl = (url, options = {}) => {
    calls.push({url: String(url), method: String(options.method || 'GET').toUpperCase(), body: options.body});
    const outcome = reply(calls.length);
    if (outcome instanceof Error) return Promise.reject(outcome);
    return Promise.resolve(outcome);
  };
  return {impl, calls};
}

/** Let the binding's awaited request settle without relying on real timers. */
async function settle() {
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
}

async function withoutGlobalFetch(body) {
  const previous = globalThis.fetch;
  globalThis.fetch = () => {
    throw new Error('the binding must use the injected fetch, never the global one');
  };
  try {
    return await body();
  } finally {
    globalThis.fetch = previous;
  }
}

function controlFor(page, id) {
  return page.grid.querySelectorAll('.save-control').find((c) => c.getAttribute('data-recipe-id') === id);
}

function visibleIds(page) {
  return page.grid
    .querySelectorAll('.recipe-card')
    .filter((card) => !card.hidden)
    .map((card) => card.getAttribute('data-recipe-id'));
}

function snapshot(control) {
  return {
    pressed: control.getAttribute('aria-pressed'),
    label: control.getAttribute('aria-label'),
    text: control.textContent,
  };
}

// ---------------------------------------------------------------------------
// FN_JS_BIND_SEARCH
// ---------------------------------------------------------------------------

test('typing narrows the cards, updates the count and keeps the empty state hidden', () => {
  const page = browsePage();
  initBrowseSearch(page.root);

  page.search.value = 'Chickpea';
  page.search.fire('input');

  assert.deepEqual(visibleIds(page), ['lemon-chickpea-salad']);
  assert.equal(page.count.textContent, '1 recipe');
  assert.equal(page.emptyState.hidden, true);
});

test('clearing the query restores every card and the full count', () => {
  const page = browsePage();
  initBrowseSearch(page.root);

  page.search.value = 'chickpea';
  page.search.fire('input');
  page.search.value = '';
  page.search.fire('input');

  assert.deepEqual(visibleIds(page), CARDS.map((card) => card.id));
  assert.equal(page.count.textContent, matchCountLabel(CARDS.length));
  assert.equal(page.emptyState.hidden, true);
});

test('a non-matching query reveals the exact server-rendered empty state', () => {
  const page = browsePage();
  initBrowseSearch(page.root);

  page.search.value = 'zzz-no-such-dish-zzz';
  page.search.fire('input');

  assert.deepEqual(visibleIds(page), []);
  assert.equal(page.count.textContent, matchCountLabel(0));
  assert.equal(page.emptyState.hidden, false);
  assert.equal(page.emptyState.textContent, EMPTY_STATE_TEXT);
});

test('the search binding does not bind on a page without a search field or grid', () => {
  const page = detailPage(CARDS[0]);
  initBrowseSearch(page.root);
  assert.equal(page.control.getAttribute('aria-pressed'), 'false');
});

// ---------------------------------------------------------------------------
// FN_JS_BIND_SAVE: the save-control state contract
// ---------------------------------------------------------------------------

test('saving a card applies the whole derived state from one boolean', async () => {
  const page = browsePage();
  const stub = fetchStub();

  await withoutGlobalFetch(async () => {
    initCookbookControls(page.root, stub.impl);
    const control = controlFor(page, 'lemon-chickpea-salad');
    const before = snapshot(control);

    control.click();
    await settle();

    const expected = saveControlState('Lemon Chickpea Salad', true);
    assert.equal(control.getAttribute('aria-pressed'), 'true');
    assert.equal(control.getAttribute('aria-label'), expected.label);
    assert.equal(control.querySelector('.save-control-mark').textContent, expected.cue);
    assert.equal(control.querySelector('.save-control-text').textContent, expected.text);
    assert.notEqual(control.textContent, before.text);
  });
});

test('the fetch stub proves save uses POST /api/cookbook with the recipe id', async () => {
  const page = browsePage();
  const stub = fetchStub(() => ({ok: true, status: 201}));

  await withoutGlobalFetch(async () => {
    initCookbookControls(page.root, stub.impl);
    controlFor(page, 'honey-roast-plums').click();
    await settle();
  });

  assert.equal(stub.calls.length, 1);
  assert.equal(stub.calls[0].url, '/api/cookbook');
  assert.equal(stub.calls[0].method, 'POST');
  assert.deepEqual(JSON.parse(stub.calls[0].body), {id: 'honey-roast-plums'});
});

test('the fetch stub proves remove uses DELETE /api/cookbook/<recipe_id>', async () => {
  const page = browsePage(['golden-oat-porridge']);
  const stub = fetchStub(() => ({ok: true, status: 200}));

  await withoutGlobalFetch(async () => {
    initCookbookControls(page.root, stub.impl);
    const control = controlFor(page, 'golden-oat-porridge');
    assert.equal(control.getAttribute('aria-pressed'), 'true');

    control.click();
    await settle();

    assert.deepEqual(snapshot(control), {
      pressed: 'false',
      label: saveControlState('Golden Oat Porridge', false).label,
      text: '+Save',
    });
  });

  assert.equal(stub.calls.length, 1);
  assert.equal(stub.calls[0].url, '/api/cookbook/golden-oat-porridge');
  assert.equal(stub.calls[0].method, 'DELETE');
});

test('the recipe-page control toggles through the same two cookbook URLs', async () => {
  const page = detailPage(CARDS[1]);
  const stub = fetchStub((call) => ({ok: true, status: call === 1 ? 201 : 200}));

  await withoutGlobalFetch(async () => {
    initCookbookControls(page.root, stub.impl);
    page.control.click();
    await settle();
    assert.equal(page.control.getAttribute('aria-pressed'), 'true');
    page.control.click();
    await settle();
    assert.equal(page.control.getAttribute('aria-pressed'), 'false');
  });

  assert.deepEqual(
    stub.calls.map((call) => [call.method, call.url]),
    [
      ['POST', '/api/cookbook'],
      ['DELETE', '/api/cookbook/lemon-chickpea-salad'],
    ],
  );
});

test('a rejected request reverts the state, label and cue instead of reporting a save', async () => {
  const page = browsePage();
  const stub = fetchStub(() => new Error('offline'));

  await withoutGlobalFetch(async () => {
    initCookbookControls(page.root, stub.impl);
    const control = controlFor(page, 'golden-oat-porridge');
    const before = snapshot(control);

    control.click();
    await settle();

    assert.equal(stub.calls.length, 1);
    assert.deepEqual(snapshot(control), before);
  });
});

test('a non-2xx response reverts the state, label and cue', async () => {
  const page = browsePage();
  const stub = fetchStub(() => ({ok: false, status: 400}));

  await withoutGlobalFetch(async () => {
    initCookbookControls(page.root, stub.impl);
    const control = controlFor(page, 'honey-roast-plums');
    const before = snapshot(control);

    control.click();
    await settle();

    assert.deepEqual(snapshot(control), before);
  });
});

test('the save binding returns quietly when the page renders no controls', async () => {
  const stub = fetchStub();
  const root = new Node('body').append(new Node('main'));

  await withoutGlobalFetch(async () => {
    initCookbookControls(root, stub.impl);
  });
  assert.equal(stub.calls.length, 0);
});

// ---------------------------------------------------------------------------
// FN_JS_REQUEST_SAVE
// ---------------------------------------------------------------------------

test('requestCookbookChange names only the two supported cookbook URLs', async () => {
  const created = fetchStub(() => ({ok: true, status: 201}));
  assert.equal(await requestCookbookChange('golden-oat-porridge', true, created.impl), true);
  assert.deepEqual(created.calls.map((call) => [call.method, call.url]), [['POST', '/api/cookbook']]);

  const removed = fetchStub(() => ({ok: true, status: 200}));
  assert.equal(await requestCookbookChange('golden-oat-porridge', false, removed.impl), true);
  assert.deepEqual(removed.calls.map((call) => [call.method, call.url]), [
    ['DELETE', '/api/cookbook/golden-oat-porridge'],
  ]);
});

test('requestCookbookChange resolves false on a rejection or a non-2xx response', async () => {
  const rejected = fetchStub(() => new Error('offline'));
  assert.equal(await requestCookbookChange('golden-oat-porridge', true, rejected.impl), false);

  for (const status of [400, 404, 500]) {
    const refused = fetchStub(() => ({ok: false, status}));
    assert.equal(await requestCookbookChange('golden-oat-porridge', true, refused.impl), false);
  }
});
