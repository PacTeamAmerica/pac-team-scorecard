#!/usr/bin/env node
/**
 * Deep render gate for the PAC TEAM Commercial Scorecard.
 *
 * Why this exists: component bodies below App() do not execute under a shallow
 * render mock. On 3 Aug 2026 a one-word typo inside Section ("score" for
 * "total") shipped and blanked the entire page while every check passed. This
 * harness invokes every function component on every tab and collects throws.
 *
 * It discovers the tabs from the file's own tab bar rather than hardcoding a
 * list, so it works on the 2-tab live build, the 7-tab re-cut, and anything
 * added later without being edited.
 *
 * Checks, per tab:
 *   - the whole createElement tree builds with zero throws
 *   - every tab button in the bar has a matching render line in the source
 *     (a button wired to nothing renders a blank tab, which is the same class
 *      of bug as the typo above)
 *
 * Usage:  node test/deeprender.js [index.html]
 * Exit 0 = pass. Exit 1 = do not publish.
 */
const fs = require('fs');

const file = process.argv[2] || 'index.html';
const html = fs.readFileSync(file, 'utf8');
const script = html.slice(html.indexOf('<script>\n') + 9, html.lastIndexOf('</script>'));

// ── discover the tabs the page actually offers ───────────────────────────────
const tabs = [];
const barRe = /data-tab="([a-zA-Z0-9_-]+)"[^>]*>([^<]*)</g;
let m;
while ((m = barRe.exec(html)) !== null) {
  if (!tabs.some(t => t.key === m[1])) {
    tabs.push({ key: m[1], label: m[2].replace(/&amp;/g, '&').trim() });
  }
}
if (!tabs.length) {
  console.log('FAIL  no tab buttons found in ' + file);
  process.exit(1);
}
const DEFAULT = tabs[0].key;

// ── every button must be wired to a render line ──────────────────────────────
let fails = 0;
console.log('TAB WIRING');
for (const t of tabs) {
  const wired = new RegExp("tab===\\s*'" + t.key + "'").test(script) ||
                t.key === DEFAULT;   // the default tab renders in the always-on block
  console.log('  ' + (wired ? 'ok  ' : 'FAIL') + '  ' + t.key.padEnd(11) + t.label);
  if (!wired) { fails++; console.log('        ! no render line for tab ' + t.key); }
}

// ── render each tab ──────────────────────────────────────────────────────────
console.log('\nDEEP RENDER  (' + file + ')');
for (const t of tabs) {
  let created = 0, invoked = 0;
  const errors = [];
  const comps = new Set();

  function walk(n) {
    if (n == null || n === false || n === true) return;
    if (Array.isArray(n)) { n.forEach(walk); return; }
    if (typeof n !== 'object') return;
    created++;
    if (typeof n.type === 'function') {
      invoked++;
      comps.add(n.type.name || 'anon');
      try { walk(n.type(n.props || {})); }
      catch (e) { errors.push((n.type.name || 'anon') + ': ' + e.message); }
      return;
    }
    if (n.props && n.props.children !== undefined) walk(n.props.children);
  }

  // The tab lives in a useState whose initial value is the default tab key.
  // Swapping that initial value is what lets one harness render every tab.
  const React = {
    createElement: (type, props, ...ch) => {
      const p = Object.assign({}, props);
      if (ch.length) p.children = ch.length === 1 ? ch[0] : ch;
      return { type, props: p };
    },
    Fragment: 'Fragment',
    useState: i => { const v = typeof i === 'function' ? i() : i; return [v === DEFAULT ? t.key : v, () => {}]; },
    useEffect: () => {}, useCallback: f => f, useMemo: f => f(), useRef: () => ({ current: null })
  };
  const doc = {
    createElement: () => ({ click() {}, style: {}, getContext: () => ({}) }),
    body: { appendChild() {}, removeChild() {} },
    getElementById: () => ({}), querySelector: () => null, querySelectorAll: () => []
  };
  const ReactDOM = { createRoot: () => ({ render(e) { walk(e); } }), render(e) { walk(e); } };
  const XLSX = { read: () => ({}), utils: { sheet_to_json: () => [] } };
  function Chart() { return { destroy() {}, update() {} }; }
  Chart.register = () => {};

  let exp;
  try {
    exp = new Function(
      'React', 'ReactDOM', 'XLSX', 'Chart', 'document', 'window', 'fetch',
      'Blob', 'URL', 'FileReader', 'setTimeout', 'alert',
      script + '\n;return {App};'
    )(React, ReactDOM, XLSX, Chart, doc, {}, () => Promise.resolve({ ok: false }),
      function () {}, { createObjectURL: () => '', revokeObjectURL() {} },
      function () {}, () => {}, () => {});
  } catch (e) {
    console.log('  FAIL  ' + t.key.padEnd(11) + 'module eval: ' + e.message);
    fails++;
    continue;
  }

  try { walk(React.createElement(exp.App, {})); }
  catch (e) { errors.push('App: ' + e.message); }

  const ok = errors.length === 0 && created > 0;
  if (!ok) fails++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + '  ' + t.key.padEnd(11) +
    String(created).padStart(5) + ' el  ' + String(invoked).padStart(4) + ' comp  ' +
    errors.length + ' err');
  errors.slice(0, 5).forEach(e => console.log('        ! ' + e));
}

console.log('\n' + (fails
  ? 'DO NOT PUBLISH - ' + fails + ' failure(s) across ' + tabs.length + ' tab(s)'
  : 'ALL ' + tabs.length + ' TAB(S) RENDER CLEAN'));
process.exit(fails ? 1 : 0);
