// Thin browse binding. Holds no decision logic: it reads server-rendered
// attributes, calls browse-logic.js and applies the result. Every recipe card is
// rendered by the server, so search only toggles the hidden attribute - no
// navigation, no reload and no request per keystroke.
//
// requestCookbookChange() is the only place a cookbook URL is named, which keeps
// the client's fetch targets auditable in one function.

import {
  emptyStateVisible,
  matchCountLabel,
  matchesRecipe,
  nextCookbook,
  saveControlState,
  titleFromControlLabel,
} from './browse-logic.js';

const SEARCH_SELECTOR = '#recipe-search';
const GRID_SELECTOR = '#recipe-grid';
const COUNT_SELECTOR = '#count';
const EMPTY_STATE_SELECTOR = '#empty-state';
const CARD_SELECTOR = '.recipe-card';
const CONTROL_SELECTOR = '.save-control';
const CUE_SELECTOR = '.save-control-mark';
const TEXT_SELECTOR = '.save-control-text';

const COOKBOOK_PATH = '/api/cookbook';

/**
 * Filter the rendered cards live as the cook types, update the match count and
 * reveal or hide the server-rendered empty state.
 *
 * Returns without binding when the search field or the card container is absent
 * (the recipe page renders neither), so the module is safe to load everywhere.
 */
export function initBrowseSearch(root = globalThis.document) {
  const scope = root;
  if (!scope || typeof scope.querySelector !== 'function') {
    return;
  }
  const search = scope.querySelector(SEARCH_SELECTOR);
  const grid = scope.querySelector(GRID_SELECTOR);
  if (!search || !grid) {
    return;
  }
  const cards = Array.from(grid.querySelectorAll(CARD_SELECTOR));
  if (cards.length === 0) {
    return;
  }
  const count = scope.querySelector(COUNT_SELECTOR);
  const emptyState = scope.querySelector(EMPTY_STATE_SELECTOR);

  const apply = () => {
    let visible = 0;
    for (const card of cards) {
      const matched = matchesRecipe(card.getAttribute('data-search-text'), search.value);
      card.hidden = !matched;
      if (matched) {
        visible += 1;
      }
    }
    if (count) {
      count.textContent = matchCountLabel(visible);
    }
    if (emptyState) {
      emptyState.hidden = !emptyStateVisible(visible);
    }
  };

  search.addEventListener('input', apply);
  // Run once so a field the browser restored on back/forward navigation cannot
  // leave a query on screen with every card visible and the full count showing.
  apply();
}

/** Apply one TYPE_SAVE_STATE to a control's state attribute, name, cue and text. */
function applySaveState(control, state) {
  control.setAttribute('aria-pressed', state.pressed ? 'true' : 'false');
  control.setAttribute('aria-label', state.label);
  const cue = control.querySelector(CUE_SELECTOR);
  if (cue) {
    cue.textContent = state.cue;
  }
  const text = control.querySelector(TEXT_SELECTOR);
  if (text) {
    text.textContent = state.text;
  }
}

/**
 * Bind the My Cookbook controls on a browse card or a recipe page.
 *
 * `fetchImpl` is injectable purely as a test seam. The optimistic state is
 * applied from one derived TYPE_SAVE_STATE and reverted when the cookbook
 * request fails, so the control never reports a save the server refused.
 */
export function initCookbookControls(root = globalThis.document, fetchImpl = globalThis.fetch) {
  const scope = root;
  if (!scope || typeof scope.querySelectorAll !== 'function') {
    return;
  }
  const controls = Array.from(scope.querySelectorAll(CONTROL_SELECTOR)).filter((control) =>
    control.getAttribute('data-recipe-id'),
  );
  if (controls.length === 0) {
    return;
  }

  const titles = new Map();
  for (const control of controls) {
    titles.set(control, titleFromControlLabel(control.getAttribute('aria-label')));
  }

  let saved = controls
    .filter((control) => control.getAttribute('aria-pressed') === 'true')
    .map((control) => control.getAttribute('data-recipe-id'));

  const render = () => {
    for (const control of controls) {
      const id = control.getAttribute('data-recipe-id');
      applySaveState(control, saveControlState(titles.get(control), saved.includes(id)));
    }
  };

  const toggle = async (control) => {
    const id = control.getAttribute('data-recipe-id');
    const next = nextCookbook(saved, id);
    const wantSaved = next.includes(id);
    saved = next;
    render();
    const accepted = await requestCookbookChange(id, wantSaved, fetchImpl);
    if (!accepted) {
      // Undo only this id. Restoring a snapshot of the whole list would discard
      // a concurrent toggle on another card that the server did accept.
      saved = nextCookbook(saved, id);
      render();
    }
  };

  for (const control of controls) {
    control.addEventListener('click', (event) => {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      void toggle(control);
    });
  }
}

/**
 * Save or remove one recipe through the supported cookbook endpoints.
 *
 * Resolves false on a network failure or a non-2xx response instead of throwing,
 * which is what lets the caller revert the control.
 */
export async function requestCookbookChange(recipeId, save, fetchImpl = globalThis.fetch) {
  const url = save ? COOKBOOK_PATH : `${COOKBOOK_PATH}/${encodeURIComponent(recipeId)}`;
  const options = save
    ? {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: recipeId}),
      }
    : {method: 'DELETE'};
  try {
    const response = await fetchImpl(url, options);
    if (!response) {
      return false;
    }
    if (typeof response.status === 'number') {
      return response.status >= 200 && response.status < 300;
    }
    return Boolean(response.ok);
  } catch {
    return false;
  }
}

// Bind the real page when the module is loaded in a browser. The test gate
// imports this module without a document, so the guard keeps the import inert.
if (globalThis.document && typeof globalThis.document.querySelector === 'function') {
  initBrowseSearch(globalThis.document);
  initCookbookControls(globalThis.document);
}
