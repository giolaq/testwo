// Acceptance tests for ticket #6: live browse search, the match count and the
// My Cookbook save controls.
//
// Scope is the remaining pure helpers of demo-app/static/browse-logic.js
// (FN_JS_NEXT_COOKBOOK, FN_JS_COUNT_LABEL, FN_JS_EMPTY_STATE, FN_JS_SAVE_LABEL)
// and the thin binding demo-app/static/browse.js (FN_JS_BIND_SEARCH,
// FN_JS_BIND_SAVE, FN_JS_REQUEST_SAVE).
//
// There is no DOM and no network in this gate, so the binding is exercised over
// a minimal element stub built here that mirrors the markup the server already
// renders (demo-app/templates/browse.html and
// demo-app/templates/_partials/{recipe_card,save_control}.html) and over an
// injected fetch stub. Card search text is taken from the committed recipe
// fixture so the expectations are deterministic and offline.
//
// Both modules are imported lazily behind a file-existence assertion so a
// missing module fails as a behaviour assertion rather than as an unhandled
// module-resolution error.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const LOGIC_URL = new URL('../browse-logic.js', import.meta.url);
const DOM_URL = new URL('../browse.js', import.meta.url);
const FIXTURE_URL = new URL('../../recipes.json', import.meta.url);

const EMPTY_STATE_TEXT = 'No recipes found. Try another ingredient or dish.';
const SEARCHABLE_FIELDS = ['title', 'description', 'category', 'dietary_tags', 'ingredients'];

// Shared expected save-control label strings. The identical list is asserted
// against the server helper cookbook_control_label() in
// demo-app/tests/test_ticket_6_save_control_parity.py, which is what holds
// FN_JS_SAVE_LABEL and FN_SAVE_CONTROL_LABEL equal (acceptance criterion 6).
const SAVE_LABEL_CASES = [
  {title: 'Golden Oat Porridge', saved: false, label: 'Add Golden Oat Porridge to My Cookbook'},
  {title: 'Golden Oat Porridge', saved: true, label: 'Remove Golden Oat Porridge from My Cookbook'},
  {title: 'Lemon Chickpea Salad', saved: false, label: 'Add Lemon Chickpea Salad to My Cookbook'},
  {title: 'Lemon Chickpea Salad', saved: true, label: 'Remove Lemon Chickpea Salad from My Cookbook'},
  {title: 'Tomato and Basil Toastie', saved: false, label: 'Add Tomato and Basil Toastie to My Cookbook'},
  {title: 'Tomato and Basil Toastie', saved: true, label: 'Remove Tomato and Basil Toastie from My Cookbook'},
];

// ---------------------------------------------------------------------------
// Module loading
// ---------------------------------------------------------------------------

async function browseLogic() {
  assert.ok(
    existsSync(fileURLToPath(LOGIC_URL)),
    'demo-app/static/browse-logic.js must exist',
  );
  const module = await import(LOGIC_URL.href);
  for (const name of ['nextCookbook', 'matchCountLabel', 'emptyStateVisible', 'saveControlState']) {
    assert.equal(
      typeof module[name],
      'function',
      `browse-logic.js must export ${name}() for ticket #6`,
    );
  }
  return module;
}

async function browseDom() {
  assert.ok(
    existsSync(fileURLToPath(DOM_URL)),
    'ticket #6 must add demo-app/static/browse.js as the thin browse binding',
  );
  const module = await import(DOM_URL.href);
  for (const name of ['initBrowseSearch', 'initCookbookControls', 'requestCookbookChange']) {
    assert.equal(
      typeof module[name],
      'function',
      `browse.js must export ${name}()`,
    );
  }
  return module;
}

function recipes() {
  return JSON.parse(readFileSync(fileURLToPath(FIXTURE_URL), 'utf8'));
}

// The JavaScript twin of the server's searchable_text(): the same five fields,
// joined with single spaces and case-folded.
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

function controlLabel(title, saved) {
  return saved ? `Remove ${title} from My Cookbook` : `Add ${title} to My Cookbook`;
}

// ---------------------------------------------------------------------------
// A minimal, dependency-free element stub
// ---------------------------------------------------------------------------

function parseCompound(raw) {
  const compound = {tag: null, id: null, classes: [], attrs: []};
  let rest = raw;
  const tag = /^[a-zA-Z][\w-]*/.exec(rest);
  if (tag) {
    compound.tag = tag[0].toLowerCase();
    rest = rest.slice(tag[0].length);
  }
  while (rest.length > 0) {
    if (rest[0] === '#') {
      const match = /^#([\w-]+)/.exec(rest);
      compound.id = match[1];
      rest = rest.slice(match[0].length);
    } else if (rest[0] === '.') {
      const match = /^\.([\w-]+)/.exec(rest);
      compound.classes.push(match[1]);
      rest = rest.slice(match[0].length);
    } else if (rest[0] === '[') {
      const match = /^\[([\w-]+)(?:([~^$*|]?=)"?([^"\]]*)"?)?\]/.exec(rest);
      compound.attrs.push({name: match[1], op: match[2] || null, value: match[3] ?? null});
      rest = rest.slice(match[0].length);
    } else {
      throw new Error(`the element stub does not support the selector part ${JSON.stringify(raw)}`);
    }
  }
  return compound;
}

function matchesCompound(element, compound) {
  if (compound.tag && element.tagName.toLowerCase() !== compound.tag) return false;
  if (compound.id && element.getAttribute('id') !== compound.id) return false;
  for (const name of compound.classes) {
    if (!element.classList.contains(name)) return false;
  }
  for (const attr of compound.attrs) {
    if (!element.hasAttribute(attr.name)) return false;
    if (attr.op === '=' && element.getAttribute(attr.name) !== attr.value) return false;
  }
  return true;
}

function matchesSelector(element, selector) {
  return String(selector)
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .some((part) => {
      const compounds = part.split(/\s+/).map(parseCompound);
      const own = compounds.pop();
      if (!matchesCompound(element, own)) return false;
      let node = element.parentNode;
      for (let index = compounds.length - 1; index >= 0; index -= 1) {
        let found = false;
        while (node) {
          if (matchesCompound(node, compounds[index])) {
            found = true;
            node = node.parentNode;
            break;
          }
          node = node.parentNode;
        }
        if (!found) return false;
      }
      return true;
    });
}

class Element {
  constructor(tagName, attributes = {}, text = '') {
    this.tagName = tagName.toUpperCase();
    this.parentNode = null;
    this.children = [];
    this.style = {};
    this._text = text;
    this._attributes = new Map();
    this._listeners = new Map();
    for (const [name, value] of Object.entries(attributes)) {
      this._attributes.set(name, String(value));
    }
    const element = this;
    this.dataset = new Proxy(
      {},
      {
        get(_target, key) {
          const name = `data-${String(key).replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`;
          return element.hasAttribute(name) ? element.getAttribute(name) : undefined;
        },
        set(_target, key, value) {
          const name = `data-${String(key).replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`;
          element.setAttribute(name, value);
          return true;
        },
        has(_target, key) {
          const name = `data-${String(key).replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`;
          return element.hasAttribute(name);
        },
      },
    );
  }

  append(...nodes) {
    for (const node of nodes) {
      node.parentNode = this;
      this.children.push(node);
    }
    return this;
  }

  getAttribute(name) {
    return this._attributes.has(name) ? this._attributes.get(name) : null;
  }

  setAttribute(name, value) {
    this._attributes.set(name, String(value));
  }

  removeAttribute(name) {
    this._attributes.delete(name);
  }

  hasAttribute(name) {
    return this._attributes.has(name);
  }

  toggleAttribute(name, force) {
    const on = force === undefined ? !this.hasAttribute(name) : Boolean(force);
    if (on) this.setAttribute(name, '');
    else this.removeAttribute(name);
    return on;
  }

  get id() {
    return this.getAttribute('id') || '';
  }

  get className() {
    return this.getAttribute('class') || '';
  }

  set className(value) {
    this.setAttribute('class', value);
  }

  get classList() {
    const element = this;
    const read = () => (element.getAttribute('class') || '').split(/\s+/).filter(Boolean);
    const write = (names) => element.setAttribute('class', names.join(' '));
    return {
      contains: (name) => read().includes(name),
      add: (...names) => write([...new Set([...read(), ...names])]),
      remove: (...names) => write(read().filter((name) => !names.includes(name))),
      toggle: (name, force) => {
        const on = force === undefined ? !read().includes(name) : Boolean(force);
        if (on) write([...new Set([...read(), name])]);
        else write(read().filter((candidate) => candidate !== name));
        return on;
      },
    };
  }

  get hidden() {
    return this.hasAttribute('hidden');
  }

  set hidden(value) {
    this.toggleAttribute('hidden', value);
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join('');
  }

  set textContent(value) {
    this.children = [];
    this._text = String(value);
  }

  get innerText() {
    return this.textContent;
  }

  set innerText(value) {
    this.textContent = value;
  }

  descendants() {
    const out = [];
    for (const child of this.children) {
      out.push(child, ...child.descendants());
    }
    return out;
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => matchesSelector(node, selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  getElementById(id) {
    return this.descendants().find((node) => node.getAttribute('id') === id) || null;
  }

  matches(selector) {
    return matchesSelector(this, selector);
  }

  closest(selector) {
    let node = this;
    while (node) {
      if (matchesSelector(node, selector)) return node;
      node = node.parentNode;
    }
    return null;
  }

  addEventListener(type, handler) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(handler);
  }

  dispatchEvent(event) {
    event.target = event.target || this;
    let node = this;
    while (node) {
      event.currentTarget = node;
      for (const handler of node._listeners.get(event.type) || []) {
        handler.call(node, event);
      }
      node = node.parentNode;
    }
    return !event.defaultPrevented;
  }

  makeEvent(type) {
    const event = {type, target: this, defaultPrevented: false};
    event.preventDefault = () => {
      event.defaultPrevented = true;
    };
    event.stopPropagation = () => {};
    return event;
  }

  click() {
    return this.dispatchEvent(this.makeEvent('click'));
  }

  input() {
    return this.dispatchEvent(this.makeEvent('input'));
  }
}

/** Build the server-rendered browse page for the first `count` fixture recipes. */
function browsePage(count = 6, savedIds = []) {
  const cards = recipes().slice(0, count);
  const root = new Element('body');
  const main = new Element('main');
  const search = new Element('input', {
    id: 'recipe-search',
    type: 'search',
    name: 'q',
    'aria-label': 'Search recipes, ingredients or dishes',
  });
  search.value = '';
  const grid = new Element('section', {class: 'recipe-grid', id: 'recipe-grid'});
  const count_ = new Element('span', {id: 'count'}, `${cards.length} recipes`);
  const emptyState = new Element('p', {class: 'empty-state', id: 'empty-state', hidden: ''}, EMPTY_STATE_TEXT);

  for (const recipe of cards) {
    const saved = savedIds.includes(recipe.id);
    const card = new Element('article', {
      class: 'recipe-card',
      'data-recipe-id': recipe.id,
      'data-search-text': searchText(recipe),
    });
    const link = new Element('a', {class: 'recipe-card-link', href: `/recipe/${recipe.id}`});
    link.append(new Element('h3', {class: 'recipe-card-title'}, recipe.title));
    const control = new Element('button', {
      class: 'save-control',
      type: 'button',
      'data-recipe-id': recipe.id,
      'aria-pressed': saved ? 'true' : 'false',
      'aria-label': controlLabel(recipe.title, saved),
    });
    control.append(
      new Element('span', {class: 'save-control-mark', 'aria-hidden': 'true'}, saved ? '✓' : '+'),
      new Element('span', {class: 'save-control-text'}, saved ? 'Saved' : 'Save'),
    );
    card.append(link, control);
    grid.append(card);
  }

  main.append(search, count_, grid, emptyState);
  root.append(main);
  return {root, search, grid, count: count_, emptyState, recipes: cards};
}

/** The server-rendered recipe page: one save control, no search field, no grid. */
function detailPage(recipe, saved = false) {
  const root = new Element('body');
  const main = new Element('main', {class: 'recipe-shell'});
  const list = new Element('ul', {class: 'recipe-actions'});
  const control = new Element('button', {
    class: 'save-control',
    type: 'button',
    'data-recipe-id': recipe.id,
    'aria-pressed': saved ? 'true' : 'false',
    'aria-label': controlLabel(recipe.title, saved),
  });
  control.append(
    new Element('span', {class: 'save-control-mark', 'aria-hidden': 'true'}, saved ? '✓' : '+'),
    new Element('span', {class: 'save-control-text'}, saved ? 'Saved' : 'Save'),
  );
  list.append(new Element('li').append(control));
  main.append(list);
  root.append(main);
  return {root, control};
}

/** A recording fetch stub. `reply` decides the response (or rejection) per call. */
function fetchStub(reply = () => ({ok: true, status: 201})) {
  const calls = [];
  const impl = (url, options = {}) => {
    calls.push({url: String(url), options});
    let outcome;
    try {
      outcome = reply(calls.length, url, options);
    } catch (error) {
      return Promise.reject(error);
    }
    if (outcome instanceof Error) return Promise.reject(outcome);
    const response = {
      ok: true,
      status: 200,
      json: async () => ({recipe_ids: []}),
      text: async () => '{}',
      ...outcome,
    };
    return Promise.resolve(response);
  };
  return {impl, calls};
}

/** Let the binding's awaited fetch settle without depending on real timers. */
async function settle() {
  for (let index = 0; index < 20; index += 1) {
    await Promise.resolve();
  }
  await new Promise((resolve) => setImmediate(resolve));
  for (let index = 0; index < 20; index += 1) {
    await Promise.resolve();
  }
}

/** Run a body with a document global present, and with fetch made unusable. */
async function withGlobals(root, body) {
  const previousDocument = globalThis.document;
  const previousFetch = globalThis.fetch;
  globalThis.document = root;
  globalThis.fetch = () => {
    throw new Error('the browse binding must not call the global fetch in this gate');
  };
  try {
    return await body();
  } finally {
    globalThis.document = previousDocument;
    globalThis.fetch = previousFetch;
  }
}

function visibleCards(page) {
  return page.grid.querySelectorAll('.recipe-card').filter((card) => !card.hidden);
}

// ---------------------------------------------------------------------------
// Pure helpers (FN_JS_NEXT_COOKBOOK, FN_JS_COUNT_LABEL, FN_JS_EMPTY_STATE)
// ---------------------------------------------------------------------------

test('nextCookbook toggles an id and preserves insertion order', async () => {
  const {nextCookbook} = await browseLogic();

  assert.deepEqual(nextCookbook([], 'lemon-chickpea-salad'), ['lemon-chickpea-salad']);
  assert.deepEqual(
    nextCookbook(['slow-simmered-lentil-stew', 'golden-oat-porridge'], 'lemon-chickpea-salad'),
    ['slow-simmered-lentil-stew', 'golden-oat-porridge', 'lemon-chickpea-salad'],
    'a new id is appended in insertion order, matching the server store rather than sorted',
  );
  assert.deepEqual(
    nextCookbook(['slow-simmered-lentil-stew', 'golden-oat-porridge', 'honey-roast-plums'], 'golden-oat-porridge'),
    ['slow-simmered-lentil-stew', 'honey-roast-plums'],
    'toggling a saved id removes it and leaves the order of the rest untouched',
  );
});

test('nextCookbook does not mutate the list it was given', async () => {
  const {nextCookbook} = await browseLogic();
  const current = ['golden-oat-porridge'];
  const next = nextCookbook(current, 'honey-roast-plums');

  assert.deepEqual(current, ['golden-oat-porridge']);
  assert.notEqual(next, current);
});

test('matchCountLabel uses recipe-domain wording and pluralises', async () => {
  const {matchCountLabel} = await browseLogic();

  assert.equal(matchCountLabel(1), '1 recipe');
  assert.equal(matchCountLabel(2), '2 recipes');
  assert.equal(matchCountLabel(13), '13 recipes');

  const zero = matchCountLabel(0);
  assert.equal(typeof zero, 'string');
  assert.match(zero, /recipe/i, 'the zero label must stay in the recipe domain');
  assert.match(zero, /^(0|no)\b/i, 'the zero label must read as a zero count');
  assert.notEqual(zero, matchCountLabel(1));
});

test('emptyStateVisible is true only when nothing matches', async () => {
  const {emptyStateVisible} = await browseLogic();

  assert.equal(emptyStateVisible(0), true);
  assert.equal(emptyStateVisible(1), false);
  assert.equal(emptyStateVisible(13), false);
});

// ---------------------------------------------------------------------------
// FN_JS_SAVE_LABEL / TYPE_SAVE_STATE
// ---------------------------------------------------------------------------

test('saveControlState derives pressed, label and a non-colour cue from one boolean', async () => {
  const {saveControlState} = await browseLogic();

  const unsaved = saveControlState('Lemon Chickpea Salad', false);
  const saved = saveControlState('Lemon Chickpea Salad', true);

  assert.equal(unsaved.pressed, false);
  assert.equal(saved.pressed, true);
  assert.equal(unsaved.label, 'Add Lemon Chickpea Salad to My Cookbook');
  assert.equal(saved.label, 'Remove Lemon Chickpea Salad from My Cookbook');

  for (const state of [unsaved, saved]) {
    assert.equal(typeof state.cue, 'string');
    assert.notEqual(state.cue.trim(), '', 'the non-colour cue must be a visible marker');
  }
  assert.notEqual(
    saved.cue,
    unsaved.cue,
    'saved and unsaved must be distinguishable without perceiving colour',
  );
});

test('saveControlState labels equal the shared expected strings from the server helper', async () => {
  const {saveControlState} = await browseLogic();

  for (const expected of SAVE_LABEL_CASES) {
    const state = saveControlState(expected.title, expected.saved);
    assert.equal(
      state.label,
      expected.label,
      `saveControlState(${JSON.stringify(expected.title)}, ${expected.saved}).label must equal the server label`,
    );
    assert.equal(state.pressed, expected.saved);
  }
});

// ---------------------------------------------------------------------------
// FN_JS_BIND_SEARCH: live filtering, count and empty state
// ---------------------------------------------------------------------------

test('typing filters the rendered cards live with no fetch and no reload', async () => {
  const {initBrowseSearch} = await browseDom();
  const {matchCountLabel} = await browseLogic();
  const page = browsePage(8);

  await withGlobals(page.root, async () => {
    initBrowseSearch(page.root);

    page.search.value = 'Chickpea';
    page.search.input();

    const expected = page.recipes.filter((recipe) => searchText(recipe).includes('chickpea'));
    assert.ok(expected.length >= 1 && expected.length < page.recipes.length, 'the query must narrow the grid');

    assert.deepEqual(
      visibleCards(page).map((card) => card.getAttribute('data-recipe-id')),
      expected.map((recipe) => recipe.id),
      'only matching cards stay visible, in server order',
    );
    for (const card of page.grid.querySelectorAll('.recipe-card')) {
      const matched = expected.some((recipe) => recipe.id === card.getAttribute('data-recipe-id'));
      assert.equal(card.hidden, !matched, `card ${card.getAttribute('data-recipe-id')} hidden state`);
    }
    assert.equal(page.count.textContent, matchCountLabel(expected.length));
    assert.equal(page.emptyState.hidden, true);
  });
});

test('clearing the query restores every card and the full count', async () => {
  const {initBrowseSearch} = await browseDom();
  const {matchCountLabel} = await browseLogic();
  const page = browsePage(8);

  await withGlobals(page.root, async () => {
    initBrowseSearch(page.root);

    page.search.value = 'chickpea';
    page.search.input();
    page.search.value = '';
    page.search.input();

    assert.equal(visibleCards(page).length, page.recipes.length);
    for (const card of page.grid.querySelectorAll('.recipe-card')) {
      assert.equal(card.hidden, false);
    }
    assert.equal(page.count.textContent, matchCountLabel(page.recipes.length));
    assert.equal(page.emptyState.hidden, true);
  });
});

test('a non-matching query shows a zero count and the exact recipe empty state', async () => {
  const {initBrowseSearch} = await browseDom();
  const {matchCountLabel} = await browseLogic();
  const page = browsePage(8);

  await withGlobals(page.root, async () => {
    initBrowseSearch(page.root);

    page.search.value = 'zzz-no-such-dish-zzz';
    page.search.input();

    assert.equal(visibleCards(page).length, 0);
    assert.equal(page.count.textContent, matchCountLabel(0));
    assert.equal(page.emptyState.hidden, false, 'the server-rendered empty state must be revealed');
    assert.equal(
      page.emptyState.textContent,
      EMPTY_STATE_TEXT,
      'the empty state keeps exactly the server-rendered wording',
    );
  });
});

test('mixed-case and whitespace-padded queries filter the same cards', async () => {
  const {initBrowseSearch} = await browseDom();
  const page = browsePage(8);

  await withGlobals(page.root, async () => {
    initBrowseSearch(page.root);

    page.search.value = 'breakfast';
    page.search.input();
    const folded = visibleCards(page).map((card) => card.getAttribute('data-recipe-id'));

    page.search.value = '  BREAKFAST  ';
    page.search.input();
    assert.deepEqual(visibleCards(page).map((card) => card.getAttribute('data-recipe-id')), folded);
    assert.ok(folded.length >= 1);
  });
});

test('the search binding returns quietly when the page has no search field or grid', async () => {
  const {initBrowseSearch} = await browseDom();
  const [recipe] = recipes();
  const page = detailPage(recipe);

  await withGlobals(page.root, async () => {
    initBrowseSearch(page.root);
  });
});

// ---------------------------------------------------------------------------
// FN_JS_BIND_SAVE / FN_JS_REQUEST_SAVE: state contract and fetch targets
// ---------------------------------------------------------------------------

test('activating an unsaved card control posts to /api/cookbook and shows the saved state', async () => {
  const {initCookbookControls} = await browseDom();
  const {saveControlState} = await browseLogic();
  const page = browsePage(3);
  const stub = fetchStub(() => ({ok: true, status: 201}));

  await withGlobals(page.root, async () => {
    initCookbookControls(page.root, stub.impl);

    const recipe = page.recipes[1];
    const control = page.grid.querySelector(`[data-recipe-id="${recipe.id}"] .save-control`);
    const before = control.textContent;
    control.click();
    await settle();

    assert.equal(stub.calls.length, 1, 'exactly one cookbook request per activation');
    assert.equal(stub.calls[0].url, '/api/cookbook');
    assert.equal(String(stub.calls[0].options.method).toUpperCase(), 'POST');
    assert.match(
      String(stub.calls[0].options.body),
      new RegExp(recipe.id),
      'the POST body must carry the recipe id',
    );

    const expected = saveControlState(recipe.title, true);
    assert.equal(control.getAttribute('aria-pressed'), 'true');
    assert.equal(control.getAttribute('aria-label'), expected.label);
    assert.ok(
      control.textContent.includes(expected.cue),
      `the control must show the saved non-colour cue ${JSON.stringify(expected.cue)}`,
    );
    assert.notEqual(control.textContent, before, 'the visible label must change with the state');
  });
});

test('activating a saved control deletes /api/cookbook/<recipe_id> and reverts the label', async () => {
  const {initCookbookControls} = await browseDom();
  const {saveControlState} = await browseLogic();
  const all = recipes();
  const recipe = all[3];
  const page = browsePage(6, [recipe.id]);
  const stub = fetchStub(() => ({ok: true, status: 200}));

  await withGlobals(page.root, async () => {
    initCookbookControls(page.root, stub.impl);

    const control = page.grid.querySelector(`[data-recipe-id="${recipe.id}"] .save-control`);
    assert.equal(control.getAttribute('aria-pressed'), 'true');

    control.click();
    await settle();

    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].url, `/api/cookbook/${recipe.id}`);
    assert.equal(String(stub.calls[0].options.method).toUpperCase(), 'DELETE');

    const expected = saveControlState(recipe.title, false);
    assert.equal(control.getAttribute('aria-pressed'), 'false');
    assert.equal(control.getAttribute('aria-label'), expected.label);
    assert.ok(control.textContent.includes(expected.cue));
  });
});

test('the detail-page control toggles through the same two cookbook URLs', async () => {
  const {initCookbookControls} = await browseDom();
  const {saveControlState} = await browseLogic();
  const [recipe] = recipes();
  const page = detailPage(recipe, false);
  const stub = fetchStub((call) => ({ok: true, status: call === 1 ? 201 : 200}));

  await withGlobals(page.root, async () => {
    initCookbookControls(page.root, stub.impl);

    page.control.click();
    await settle();
    assert.equal(page.control.getAttribute('aria-pressed'), 'true');
    assert.equal(page.control.getAttribute('aria-label'), saveControlState(recipe.title, true).label);

    page.control.click();
    await settle();
    assert.equal(page.control.getAttribute('aria-pressed'), 'false');
    assert.equal(page.control.getAttribute('aria-label'), saveControlState(recipe.title, false).label);

    assert.deepEqual(
      stub.calls.map((call) => [String(call.options.method).toUpperCase(), call.url]),
      [
        ['POST', '/api/cookbook'],
        ['DELETE', `/api/cookbook/${recipe.id}`],
      ],
      'the client names no cookbook URL other than the two supported ones',
    );
  });
});

test('the client requests no URL outside the cookbook endpoints', async () => {
  const {initCookbookControls} = await browseDom();
  const page = browsePage(4);
  const stub = fetchStub(() => ({ok: true, status: 201}));

  await withGlobals(page.root, async () => {
    initCookbookControls(page.root, stub.impl);
    for (const control of page.grid.querySelectorAll('.save-control')) {
      control.click();
      await settle();
    }
  });

  assert.equal(stub.calls.length, 4);
  for (const call of stub.calls) {
    assert.match(
      call.url,
      /^\/api\/cookbook(\/[a-z0-9-]+)?$/,
      `the client must not request ${call.url}`,
    );
  }
});

test('a rejected cookbook request reverts the control state, label and cue', async () => {
  const {initCookbookControls} = await browseDom();
  const page = browsePage(3);
  const stub = fetchStub(() => new Error('offline'));

  await withGlobals(page.root, async () => {
    initCookbookControls(page.root, stub.impl);

    const recipe = page.recipes[0];
    const control = page.grid.querySelector(`[data-recipe-id="${recipe.id}"] .save-control`);
    const label = control.getAttribute('aria-label');
    const cue = control.textContent;

    control.click();
    await settle();

    assert.equal(stub.calls.length, 1);
    assert.equal(control.getAttribute('aria-pressed'), 'false', 'a network failure must not report a save');
    assert.equal(control.getAttribute('aria-label'), label);
    assert.equal(control.textContent, cue);
  });
});

test('a non-2xx cookbook response reverts the control state, label and cue', async () => {
  const {initCookbookControls} = await browseDom();
  const page = browsePage(3);
  const stub = fetchStub(() => ({ok: false, status: 400, json: async () => ({error: 'Unknown recipe'})}));

  await withGlobals(page.root, async () => {
    initCookbookControls(page.root, stub.impl);

    const recipe = page.recipes[2];
    const control = page.grid.querySelector(`[data-recipe-id="${recipe.id}"] .save-control`);
    const label = control.getAttribute('aria-label');
    const cue = control.textContent;

    control.click();
    await settle();

    assert.equal(control.getAttribute('aria-pressed'), 'false');
    assert.equal(control.getAttribute('aria-label'), label);
    assert.equal(control.textContent, cue);
  });
});

test('requestCookbookChange resolves true on success and false on failure', async () => {
  const {requestCookbookChange} = await browseDom();

  const created = fetchStub(() => ({ok: true, status: 201}));
  assert.equal(await requestCookbookChange('golden-oat-porridge', true, created.impl), true);
  assert.equal(created.calls[0].url, '/api/cookbook');
  assert.equal(String(created.calls[0].options.method).toUpperCase(), 'POST');

  const removed = fetchStub(() => ({ok: true, status: 200}));
  assert.equal(await requestCookbookChange('golden-oat-porridge', false, removed.impl), true);
  assert.equal(removed.calls[0].url, '/api/cookbook/golden-oat-porridge');
  assert.equal(String(removed.calls[0].options.method).toUpperCase(), 'DELETE');

  const rejected = fetchStub(() => new Error('offline'));
  assert.equal(
    await requestCookbookChange('golden-oat-porridge', true, rejected.impl),
    false,
    'a rejected request resolves false instead of throwing',
  );

  const refused = fetchStub(() => ({ok: false, status: 400}));
  assert.equal(await requestCookbookChange('golden-oat-porridge', true, refused.impl), false);
});

test('the save binding returns quietly when the page has no save controls', async () => {
  const {initCookbookControls} = await browseDom();
  const stub = fetchStub();
  const root = new Element('body').append(new Element('main'));

  await withGlobals(root, async () => {
    initCookbookControls(root, stub.impl);
  });
  assert.equal(stub.calls.length, 0);
});
