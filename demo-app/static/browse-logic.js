// Dependency-free browse logic. Imports nothing and touches no DOM, so
// `node --test` can import it directly. The two helpers here mirror the server
// definitions in demo-app/recipe_search.py (normalise_query and the containment
// rule over searchable_text) so client and server search the same characters.
// The DOM binding, the cookbook toggle and the count/empty-state helpers land in
// T-MOBCLIENT.

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
