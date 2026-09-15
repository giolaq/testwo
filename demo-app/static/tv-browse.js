// TV browse DOM binding. Holds no decision logic: it reads the rail and card
// counts from the rendered data attributes, asks the pure focus model in
// tv-logic.js what the next focus state is, then applies and scrolls it.

import {nextFocus} from './tv-logic.js';

const CARD_SELECTOR = '[data-rail-index][data-card-index]';
const HANDLED_KEYS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']);

/** Cards grouped by rail index, each rail in rendered card-index order. */
function readRails(root) {
  const rails = [];
  for (const card of root.querySelectorAll(CARD_SELECTOR)) {
    const railIndex = Number(card.getAttribute('data-rail-index'));
    const cardIndex = Number(card.getAttribute('data-card-index'));
    if (!Number.isInteger(railIndex) || !Number.isInteger(cardIndex)) {
      continue;
    }
    while (rails.length <= railIndex) {
      rails.push([]);
    }
    rails[railIndex][cardIndex] = card;
  }
  return rails.map((cards) => [...cards].filter(Boolean));
}

/** Keep the focused card fully on screen; a no-op where the API is missing. */
export function scrollFocusIntoView(card) {
  if (card && typeof card.scrollIntoView === 'function') {
    card.scrollIntoView({block: 'nearest', inline: 'center'});
  }
}

/**
 * Open the focused recipe using the href the server already rendered, so mode
 * retention is never re-derived here and cannot disagree with the server.
 */
export function openFocused(card) {
  const link = card && card.matches('a[href]') ? card : card && card.querySelector('a[href]');
  const href = link && link.getAttribute('href');
  if (!href) {
    return;
  }
  globalThis.location?.assign(href);
}

/** Reuse the shared mobile save-control binding once it is available. */
async function bindSaveControls(root) {
  // Only the resolution of the shared module is optional: it does not exist
  // until the mobile browse client lands. A failure inside the binding itself
  // must surface rather than leave TV save controls silently inert.
  const module = await import('./browse.js').catch(() => null);
  if (module && typeof module.initCookbookControls === 'function') {
    module.initCookbookControls(root);
  }
}

export function initTvBrowse(root = globalThis.document) {
  if (!root || typeof root.querySelectorAll !== 'function') {
    return;
  }
  const rails = readRails(root);
  const railCounts = rails.map((cards) => cards.length);
  if (!railCounts.some((count) => count > 0)) {
    return;
  }

  let state = {railIndex: railCounts.findIndex((count) => count > 0), cardIndex: 0};

  const apply = (next) => {
    state = next;
    const card = rails[state.railIndex]?.[state.cardIndex];
    if (!card) {
      return;
    }
    for (const rail of rails) {
      for (const other of rail) {
        other.setAttribute('tabindex', other === card ? '0' : '-1');
      }
    }
    if (typeof card.focus === 'function') {
      card.focus();
    }
    scrollFocusIntoView(card);
  };

  apply(state);

  /** The card the event happened in, so the model follows real focus. */
  const cardOf = (target) => target?.closest?.(CARD_SELECTOR) ?? null;

  // Tab can reach a card (or the anchor inside it) without an arrow key, so the
  // model is resynchronised from whatever actually holds focus.
  root.addEventListener('focusin', (event) => {
    const card = cardOf(event.target);
    if (!card) {
      return;
    }
    const railIndex = Number(card.getAttribute('data-rail-index'));
    const cardIndex = Number(card.getAttribute('data-card-index'));
    if (rails[railIndex]?.[cardIndex] === card) {
      state = {railIndex, cardIndex};
    }
  });

  root.addEventListener('keydown', (event) => {
    if (HANDLED_KEYS.has(event.key)) {
      event.preventDefault();
      apply(nextFocus(state, railCounts, event.key));
      return;
    }
    if (event.key === 'Enter') {
      // Let a focused control or link handle its own native activation.
      if (event.target?.closest?.('button, a[href]')) {
        return;
      }
      const card = cardOf(event.target) ?? rails[state.railIndex]?.[state.cardIndex];
      if (!card) {
        return;
      }
      event.preventDefault();
      openFocused(card);
    }
  });

  bindSaveControls(root);
}

if (globalThis.document) {
  initTvBrowse(globalThis.document);
}
