// The pure TV focus model: dependency-free, DOM-free and total.
//
// Every transition is a pure function of the previous focus state, the rendered
// per-rail card counts and the key name, which is what makes remote navigation
// verifiable offline under `node --test`. The DOM binding in tv-browse.js only
// applies what these functions decide.

/**
 * Keep an index inside a rail of `count` cards.
 *
 * Below zero clamps to the first card, past the end clamps to the last one, and
 * an empty rail yields 0 - callers must not focus an empty rail.
 */
export function clampIndex(index, count) {
  const size = Number.isFinite(count) ? Math.trunc(count) : 0;
  if (size <= 0) {
    return 0;
  }
  if (!Number.isFinite(index)) {
    return 0;
  }
  const position = Math.trunc(index);
  if (position < 0) {
    return 0;
  }
  return Math.min(position, size - 1);
}

/**
 * The next focus state for an arrow key.
 *
 * ArrowLeft and ArrowRight move within the current rail and clamp at its first
 * and last card without wrapping. ArrowUp and ArrowDown change rail and clamp
 * the card index to the nearest valid position in the destination rail. A
 * destination rail that is out of range or empty leaves focus where it is, and
 * any other key returns the state unchanged.
 */
export function nextFocus(state, railCounts, key) {
  const counts = Array.isArray(railCounts) ? railCounts : [];
  const railIndex = Number.isFinite(state?.railIndex) ? Math.trunc(state.railIndex) : 0;
  const cardIndex = Number.isFinite(state?.cardIndex) ? Math.trunc(state.cardIndex) : 0;
  const unchanged = {railIndex, cardIndex};
  const currentCount = Number.isFinite(counts[railIndex]) ? Math.trunc(counts[railIndex]) : 0;

  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const step = key === 'ArrowRight' ? 1 : -1;
    return {railIndex, cardIndex: clampIndex(cardIndex + step, currentCount)};
  }

  if (key === 'ArrowUp' || key === 'ArrowDown') {
    const destination = railIndex + (key === 'ArrowDown' ? 1 : -1);
    if (destination < 0 || destination >= counts.length) {
      return unchanged;
    }
    const destinationCount = Number.isFinite(counts[destination])
      ? Math.trunc(counts[destination])
      : 0;
    if (destinationCount <= 0) {
      return unchanged;
    }
    return {railIndex: destination, cardIndex: clampIndex(cardIndex, destinationCount)};
  }

  return unchanged;
}
