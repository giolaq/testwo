// Dependency-free browse logic. Imports nothing and touches no DOM, so
// `node --test` can import it directly. The search helpers mirror the server
// definitions in demo-app/recipe_search.py (normalise_query and the containment
// rule over searchable_text) so client and server search the same characters,
// and the save-control helper mirrors cookbook_control_label() in
// demo-app/page_routes.py so the label the server renders is the one the client
// reproduces. demo-app/static/browse.js is the only DOM consumer of this module.

/** Trim and case-fold a raw query; anything non-string means "match everything". */
export function normaliseQuery(value) {
  if (typeof value !== 'string') {
    return '';
  }
  return value.trim().toLowerCase();
}

/** True when the normalised query is contained in a card's searchable text. */
export function matchesRecipe(searchText, value) {
  const query = normaliseQuery(value);
  if (query === '') {
    return true;
  }
  return String(searchText).toLowerCase().includes(query);
}

/**
 * Toggle one recipe id in the saved-id list.
 *
 * Insertion order is preserved rather than sorted, matching the server store
 * (CookbookStore keeps dict insertion order), so the client view of My Cookbook
 * and GET /api/cookbook agree. The input list is never mutated.
 */
export function nextCookbook(current, id) {
  const ids = Array.isArray(current) ? [...current] : [];
  const at = ids.indexOf(id);
  if (at === -1) {
    ids.push(id);
    return ids;
  }
  ids.splice(at, 1);
  return ids;
}

/** Recipe-domain match count: '1 recipe', 'N recipes', '0 recipes' for none. */
export function matchCountLabel(visible) {
  const count = Number.isFinite(visible) ? Math.max(0, Math.trunc(visible)) : 0;
  return count === 1 ? '1 recipe' : `${count} recipes`;
}

/**
 * Whether the empty state should be shown. The exact wording
 * ('No recipes found. Try another ingredient or dish.') lives in the browse
 * template and is only revealed here, so it is defined in one place.
 */
export function emptyStateVisible(visible) {
  const count = Number.isFinite(visible) ? Math.max(0, Math.trunc(visible)) : 0;
  return count === 0;
}

/**
 * The save-control state (TYPE_SAVE_STATE) derived from one boolean:
 * the ARIA pressed value, the recipe-naming accessible label, a non-colour cue
 * and the visible text. One source means the four presentations cannot drift.
 */
export function saveControlState(title, saved) {
  const name = typeof title === 'string' ? title : String(title ?? '');
  const pressed = Boolean(saved);
  return {
    pressed,
    label: pressed
      ? `Remove ${name} from My Cookbook`
      : `Add ${name} to My Cookbook`,
    cue: pressed ? '✓' : '+',
    text: pressed ? 'Saved' : 'Save',
  };
}

// A character no recipe title contains, used to locate the title slot inside a
// rendered label without restating the label grammar below.
const TITLE_SLOT = '\u0001';

/**
 * Recover a recipe title from a control's rendered accessible name.
 *
 * The binding needs the title to build the label for the *other* state, and the
 * server-rendered control is the only place the title appears on a detail page.
 * Inverting through saveControlState() keeps the wording owned by this module.
 */
export function titleFromControlLabel(label) {
  const text = typeof label === 'string' ? label : '';
  for (const saved of [false, true]) {
    const pattern = saveControlState(TITLE_SLOT, saved).label;
    const slot = pattern.indexOf(TITLE_SLOT);
    const head = pattern.slice(0, slot);
    const tail = pattern.slice(slot + TITLE_SLOT.length);
    if (
      text.length > head.length + tail.length &&
      text.startsWith(head) &&
      text.endsWith(tail)
    ) {
      return text.slice(head.length, text.length - tail.length);
    }
  }
  return '';
}
