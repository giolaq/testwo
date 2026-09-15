// Acceptance tests for ticket #5: measured WCAG contrast of the TableStory brand
// tokens, read from demo-app/static/styles.css.
//
// The WCAG arithmetic lives here (and only here) so the recorded contrast table has a
// single executable definition; test_ticket_5_brand_stylesheet.py covers the
// structural stylesheet rules and the rendered browse surface.
//
// Everything is offline and deterministic: the stylesheet is read from disk, the
// tokens are resolved through their var() chains, and the ratios are computed with the
// WCAG 2.1 relative-luminance formula. No DOM, no network, no dependency.
//
// Note on the approved palette: tomato red #C9472D on cream #FFF8ED measures
// 4.50:1 to two decimals but 4.4999:1 exactly, so it satisfies WCAG AA for large or
// bold text and for user-interface components (3:1) rather than for small body text.
// The thresholds below encode that: charcoal text carries body copy at >= 4.5:1, and
// the primary action and focus ring are held to the 3:1 component floor.

import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const STYLES_PATH = fileURLToPath(new URL('../styles.css', import.meta.url));

const APPROVED = {
  surface: {hex: '#fff8ed', roles: ['surface', 'cream', 'canvas']},
  primary: {hex: '#c9472d', roles: ['primary', 'action', 'active', 'accent-warm']},
  saved: {hex: '#3f6b4f', roles: ['saved', 'cookbook', 'herb']},
  text: {hex: '#26231f', roles: ['text', 'ink']},
  highlight: {hex: '#e9b44c', roles: ['highlight', 'accent']},
};

function readStylesheet() {
  assert.ok(existsSync(STYLES_PATH), `expected the brand stylesheet at ${STYLES_PATH}`);
  return readFileSync(STYLES_PATH, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
}

function rootTokens(css) {
  const tokens = new Map();
  const blocks = css.match(/:root[^{]*\{[^}]*\}/g) ?? [];
  for (const block of blocks) {
    const body = block.slice(block.indexOf('{') + 1, -1);
    for (const declaration of body.split(';')) {
      const index = declaration.indexOf(':');
      if (index === -1) continue;
      const name = declaration.slice(0, index).trim().toLowerCase();
      if (!name.startsWith('--')) continue;
      tokens.set(name, declaration.slice(index + 1).trim().toLowerCase());
    }
  }
  return tokens;
}

function resolve(value, tokens, depth = 0) {
  const trimmed = String(value).trim().toLowerCase();
  const match = /^var\(\s*(--[\w-]+)\s*(?:,([\s\S]*))?\)$/.exec(trimmed);
  if (match && depth < 8) {
    const [, name, fallback] = match;
    if (tokens.has(name)) return resolve(tokens.get(name), tokens, depth + 1);
    if (fallback) return resolve(fallback, tokens, depth + 1);
  }
  return trimmed;
}

function relativeLuminance(hex) {
  let raw = hex.replace('#', '');
  if (raw.length === 3) raw = [...raw].map((c) => c + c).join('');
  const channels = [0, 2, 4].map((i) => parseInt(raw.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(a, b) {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function tokenFor(role, tokens) {
  const {hex, roles} = APPROVED[role];
  for (const [name, value] of tokens) {
    if (!value.startsWith(hex)) continue;
    if (roles.some((word) => name.includes(word))) return name;
  }
  return null;
}

test('the stylesheet declares each approved colour under a role-named token', () => {
  const tokens = rootTokens(readStylesheet());
  assert.ok(tokens.size > 0, 'the stylesheet declares no :root custom properties');
  for (const role of Object.keys(APPROVED)) {
    const name = tokenFor(role, tokens);
    assert.ok(
      name,
      `no role-named custom property carries ${APPROVED[role].hex} for the ${role} role ` +
        `(declared tokens: ${[...tokens.keys()].join(', ') || 'none'})`,
    );
    assert.equal(
      resolve(`var(${name})`, tokens).slice(0, 7),
      APPROVED[role].hex,
      `${name} does not resolve to ${APPROVED[role].hex}`,
    );
  }
});

test('measured contrast of body text, primary action and saved state meets WCAG AA', () => {
  const tokens = rootTokens(readStylesheet());
  const value = (role) => {
    const name = tokenFor(role, tokens);
    assert.ok(name, `the ${role} token is missing, so its contrast cannot be measured`);
    return resolve(`var(${name})`, tokens).slice(0, 7);
  };

  const surface = value('surface');
  const measurements = [
    ['body text on surface', value('text'), surface, 4.5],
    ['primary action on surface', value('primary'), surface, 3.0],
    ['saved state on surface', value('saved'), surface, 4.5],
    ['surface on primary action', surface, value('primary'), 3.0],
    ['surface on saved state', surface, value('saved'), 4.5],
    ['body text on highlight', value('text'), value('highlight'), 4.5],
  ];

  for (const [label, foreground, background, floorRatio] of measurements) {
    const ratio = contrast(foreground, background);
    assert.ok(
      ratio >= floorRatio,
      `${label}: ${foreground} on ${background} measures ${ratio.toFixed(2)}:1, ` +
        `below the ${floorRatio}:1 WCAG AA floor`,
    );
  }
});

test('the highlight colour is never used to carry body text on the surface', () => {
  const tokens = rootTokens(readStylesheet());
  const highlight = tokenFor('highlight', tokens);
  assert.ok(highlight, 'the highlight token is missing');
  // #E9B44C on #FFF8ED measures 1.79:1, so it can only be a fill, border or accent.
  assert.ok(
    contrast(APPROVED.highlight.hex, APPROVED.surface.hex) < 4.5,
    'palette changed: re-check whether highlight may carry text',
  );
  const css = readStylesheet();
  const bodyText = /(?:^|[;{\s])color\s*:\s*var\(\s*--[\w-]*(?:highlight|accent)[\w-]*\s*\)/i;
  assert.ok(
    !bodyText.test(css),
    `the stylesheet sets text colour from ${highlight}, which is 1.79:1 against the cream surface`,
  );
});

test('the focus ring colour is high contrast against the cream surface', () => {
  const css = readStylesheet();
  const tokens = rootTokens(css);
  const focusBlocks = [...css.matchAll(/([^{}]*:focus[^{]*)\{([^}]*)\}/g)];
  assert.ok(focusBlocks.length > 0, 'the stylesheet defines no focus styling');

  const colours = new Set();
  for (const [, , body] of focusBlocks) {
    for (const declaration of body.split(';')) {
      const index = declaration.indexOf(':');
      if (index === -1) continue;
      const name = declaration.slice(0, index).trim().toLowerCase();
      if (!['outline', 'outline-color', 'box-shadow'].includes(name)) continue;
      const value = declaration.slice(index + 1);
      for (const reference of value.match(/var\(\s*--[\w-]+\s*\)/g) ?? []) {
        colours.add(resolve(reference, tokens).slice(0, 7));
      }
      for (const literal of value.match(/#[0-9a-f]{6}\b/gi) ?? []) {
        colours.add(literal.toLowerCase());
      }
    }
  }

  const hexes = [...colours].filter((c) => /^#[0-9a-f]{6}$/.test(c));
  assert.ok(hexes.length > 0, 'the focus ring has no resolvable colour');
  for (const colour of hexes) {
    const ratio = contrast(colour, APPROVED.surface.hex);
    assert.ok(
      ratio >= 3.0,
      `focus ring colour ${colour} measures ${ratio.toFixed(2)}:1 against the cream surface, ` +
        'below the 3:1 floor for a visible high-contrast ring',
    );
  }
});
