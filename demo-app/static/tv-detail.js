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
import {initCookbookControls} from './browse.js';

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
    const index = actions.findIndex(
      (action) => action === event.target || action.contains?.(event.target),
    );
    if (index !== -1) {
      focusIndex = index;
    }
  });

  // The shared mobile binding owns the My Cookbook control's state, so the TV
  // control behaves identically to the mobile one and there is exactly one state
  // machine per control. Importing browse.js already ran initCookbookControls
  // over the document, so binding the document again here would give the control
  // two independently-stateful click handlers; only another root still needs it.
  if (root !== globalThis.document) {
    initCookbookControls(root);
  }

  root.addEventListener('keydown', (event) => {
    const intent = resolveDetailKey(event.key, focusIndex, actions.length);

    if (intent.action === 'back') {
      event.preventDefault?.();
      navigate(backHref);
      return;
    }

    if (intent.action === 'activate') {
      const action = actions[intent.focusIndex];
      if (!action) {
        return;
      }
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
