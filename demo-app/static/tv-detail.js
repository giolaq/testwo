// TV detail DOM binding. Holds no decision logic: every key goes through the
// pure action model in tv-logic.js, and the My Cookbook action is delegated to
// the shared mobile save-control binding (initCookbookControls in browse.js) so
// the TV control cannot drift from the mobile one and every activation - remote
// Enter, a native button activation or a pointer - runs through one state
// machine rather than two that can disagree about what is saved.
//
// The action list is the two stacked primary actions the remote must reach: the
// back action first, then the My Cookbook control. Their order in the rendered
// markup is the contract with resolveDetailKey's focus indices.

import {resolveDetailKey} from './tv-logic.js';
// Imported for its module body only: browse.js binds initCookbookControls over
// the document when it loads, and that single binding owns the My Cookbook
// control's state on this page too. Nothing here calls it again, because a
// second binding on the same control would give it two independently-stateful
// click handlers.
import './browse.js';

const ACTION_LIST_SELECTOR = '[data-tv-actions]';
const ACTION_SELECTOR = 'a[href], button';

/** Navigate using an href the server already rendered, never one derived here. */
function navigate(href) {
  if (href) {
    globalThis.location?.assign(href);
  }
}

/**
 * Bind arrow-key focus movement, Enter activation and the back keys on the TV
 * recipe page.
 *
 * Returns without binding when no TV action list is rendered - the mobile recipe
 * page and the TV browse page render none - so the module is safe to load
 * anywhere and a stray remote key has nothing to act on.
 *
 * Precondition for a caller that passes its own `root`: the My Cookbook control
 * inside it must already be bound by `initCookbookControls` (from ./browse.js),
 * exactly once. This function never binds it, so a root that the document-wide
 * auto-bind cannot reach has to be bound by its caller.
 */
export function initTvDetail(root = globalThis.document) {
  if (!root || typeof root.querySelector !== 'function') {
    return;
  }
  const list = root.querySelector(ACTION_LIST_SELECTOR);
  if (!list || typeof list.querySelectorAll !== 'function') {
    return;
  }
  const actions = Array.from(list.querySelectorAll(ACTION_SELECTOR));
  if (actions.length === 0) {
    return;
  }

  // The back action is whichever action carries a browse href; index 0 by
  // contract, but read from the markup so the destination is never re-derived.
  const backHref =
    actions
      .map((action) => action.getAttribute?.('href'))
      .find((href) => typeof href === 'string' && href) ?? null;

  /** Which action, if any, an event target sits in; -1 when it is outside them. */
  const indexOfTarget = (target) =>
    actions.findIndex((action) => action === target || action.contains?.(target));

  let focusIndex = 0;

  const apply = (next) => {
    focusIndex = next;
    actions.forEach((action, index) => {
      action.setAttribute('tabindex', index === focusIndex ? '0' : '-1');
    });
    const action = actions[focusIndex];
    if (action && typeof action.focus === 'function') {
      action.focus();
    }
  };

  apply(focusIndex);

  // Tab, or a pointer, can move real focus without an arrow key, so the model is
  // resynchronised from whatever actually holds it.
  root.addEventListener('focusin', (event) => {
    const index = indexOfTarget(event.target);
    if (index !== -1) {
      focusIndex = index;
    }
  });

  root.addEventListener('keydown', (event) => {
    const intent = resolveDetailKey(event.key, focusIndex, actions.length);

    if (intent.action === 'back') {
      event.preventDefault?.();
      navigate(backHref);
      return;
    }

    if (intent.action === 'activate') {
      // Activate whatever actually holds focus, not whatever the model last
      // pointed at. Focus can sit outside the action list - the brand link is
      // focusable too - and taking over Enter there would replace the user's own
      // activation with an unrelated action.
      const index = indexOfTarget(event.target);
      if (index === -1) {
        return;
      }
      const action = actions[index];
      // Suppress the browser's own Enter activation so the action runs exactly
      // once, whichever element type holds focus: a link is followed here, and a
      // control is activated through the one click handler that owns its state.
      event.preventDefault?.();
      const href = action.getAttribute?.('href');
      if (href) {
        navigate(href);
      } else if (typeof action.click === 'function') {
        action.click();
      }
      return;
    }

    if (intent.focusIndex !== focusIndex) {
      event.preventDefault?.();
      apply(intent.focusIndex);
    }
  });
}

// Bind the real page when the module is loaded in a browser. The test gate
// imports this module without a document, so the guard keeps the import inert.
if (globalThis.document && typeof globalThis.document.querySelector === 'function') {
  initTvDetail(globalThis.document);
}
