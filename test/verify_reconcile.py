"""Cross-panel reconciliation gate.

Why this exists. On 4 Nov 2026 the shipped scorecard had two tabs reporting
different revenue: the Commercial Scorecard said $14,176,813 and Coverage &
Attainment, the tab labelled CEO metric #2, said $13,930,552. Concentration Risk
and Backlog to Cash carried the same stale open-order figure. Six panel seeds
were a week or more behind while the headline had moved on.

Every existing gate passed. verify_stale.py checks a fixed list of named figures
(invMeta.net against MONTHLY_2026, the client counts, NS_SEED.totalOrders and two
QUOTE_SEED fields) and then scans rendered text for 'M/D/2026' and 'Oct D 2026'
date strings. The stale panels matched neither shape: their dates are ISO inside
seed objects and their figures are plain integers. The gate passed a file that
contradicted itself.

So this asserts the thing that actually matters to a reader: every panel that
carries a copy of a headline figure must agree with the build, and every panel
must be stamped with the current cycle date.

It also carries the prior-month restatement check. October restated upward by
$357,700 in the two days after the 2 Nov pull, which is normal behaviour the
manual already warns about, but it moved the Score and nobody would have seen it.
Comparing MONTHLY_2026 against the previous build's values makes a restatement
something the build reports rather than something discovered later.

Usage:
  python3 -I verify_reconcile.py <build>.html build_meta.json [prev_build_meta.json]
Exit 0 = pass. Exit 1 = do not publish.
"""
import sys, re, json

html = open(sys.argv[1], encoding='utf8').read()
meta = json.load(open(sys.argv[2]))
prev = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None

CYCLE_ISO = meta.get('nsAsof') or meta.get('asof')
assert CYCLE_ISO, 'build_meta carries no as-of date'
fails, warns = [], []


def seg(name, span=3000):
    i = html.find('const ' + name)
    return html[i:i + span] if i >= 0 else ''


def const_json(name):
    """Parse a baked seed as JSON. Regex-scraping a key matches the first
    occurrence anywhere in the object, which read PIPE_SEED.flat as the Commit
    row's flat value nested inside cats[] and reported a $550,110 phantom
    disagreement. Parsing gets the top-level key."""
    i = html.find('const ' + name)
    if i < 0:
        return None
    j = html.find('=', i)
    k = html.find(';\n', j)
    if k < 0:
        return None
    try:
        return json.loads(html[j + 1:k].strip())
    except Exception:
        return None


def num(name, key):
    o = const_json(name)
    if isinstance(o, dict) and key in o and isinstance(o[key], (int, float)):
        return float(o[key])
    s = seg(name)
    if not s:
        return None
    m = re.search(r'["\']?\b' + key + r'\b["\']?\s*:\s*(-?[\d.]+)', s)
    return float(m.group(1)) if m else None


def asof(name):
    o = const_json(name)
    if isinstance(o, dict) and isinstance(o.get('asof'), str):
        return o['asof']
    m = re.search(r'["\']?asof["\']?\s*:\s*[\'"]([^\'"]+)[\'"]', seg(name))
    return m.group(1) if m else None


print('CROSS-PANEL RECONCILIATION  (cycle %s)' % CYCLE_ISO)

# ── 1. every copy of a headline figure must agree ───────────────────────
CUR = {
    'revYTD': meta['net'],
    'openUnb': round(meta['openTot']),
    'confirmed': round(meta['confT']),
    'awaiting': round(meta['awaT']),
    'wtd': meta['headlineWtd'],
}
CHECKS = [
    ('COVERAGE_SEED', 'revYTD', 'revYTD'), ('COVERAGE_SEED', 'openUnb', 'openUnb'),
    ('COVERAGE_SEED', 'confirmed', 'confirmed'), ('COVERAGE_SEED', 'awaiting', 'awaiting'),
    ('COVERAGE_SEED', 'wtd', 'wtd'),
    ('CONC_SEED', 'backlog', 'openUnb'),
    ('VELO_SEED', 'openTot', 'openUnb'),
    ('REVTIMING_SEED', 'openTot', 'openUnb'),
    ('PIPE_SEED', 'flat', 'wtd'),
]
print('\n  %-16s %-12s %16s %16s' % ('panel', 'field', 'panel says', 'build says'))
for panel, field, key in CHECKS:
    v = num(panel, field)
    c = CUR[key]
    if v is None:
        warns.append('%s.%s not found' % (panel, field))
        print('  %-16s %-12s %16s %16s   NOT FOUND' % (panel, field, '-', format(int(c), ',')))
        continue
    ok = abs(v - c) < 1.5
    if not ok:
        fails.append('%s.%s is %s, build says %s (difference %s)'
                     % (panel, field, format(int(v), ','), format(int(c), ','),
                        format(int(v - c), ',')))
    print('  %-16s %-12s %16s %16s   %s'
          % (panel, field, format(int(v), ','), format(int(c), ','), 'ok' if ok else 'DISAGREES'))

# ── 2. every panel must be stamped with the cycle date ──────────────────
PANELS = ['CEO_SEED', 'COVERAGE_SEED', 'CONC_SEED', 'VELO_SEED', 'DQ_SEED',
          'OPPS_SEED', 'SVEL_SEED', 'REVTIMING_SEED', 'PIPE_SEED', 'OPS_SEED']
# OPS_SEED is knowingly behind, pending four answers from Operations. It is
# listed so the gate reports it every build rather than letting it be forgotten.
# OPPS_SEED needs a Jobs & Opportunities export, which is not part of the four
# weekly files; it moves only when that app is exported.
ALLOWED_BEHIND = {'OPS_SEED', 'CALIB_SEED', 'OPPS_SEED'}
print('\n  panel as-of dates')
for p in PANELS:
    a = asof(p)
    if a is None:
        print('  %-16s (no asof field)' % p)
        continue
    if a == CYCLE_ISO:
        print('  %-16s %s   ok' % (p, a))
    elif p in ALLOWED_BEHIND:
        warns.append('%s is at %s, behind the %s cycle (known)' % (p, a, CYCLE_ISO))
        print('  %-16s %s   behind, allowed' % (p, a))
    else:
        fails.append('%s is stamped %s, not the %s cycle' % (p, a, CYCLE_ISO))
        print('  %-16s %s   STALE' % (p, a))

# ── 3. module-level as-of constants ─────────────────────────────────────
print('\n  module as-of constants')
for cname in ('PODIO_ASOF', 'NS_ASOF', 'SHIP_ASOF'):
    m = re.search(r"const " + cname + r"\s*=\s*'([^']+)'", html)
    if not m:
        fails.append('%s not found' % cname)
        continue
    ok = m.group(1) == CYCLE_ISO
    if not ok:
        fails.append('%s is %s, not %s' % (cname, m.group(1), CYCLE_ISO))
    print('  %-16s %s   %s' % (cname, m.group(1), 'ok' if ok else 'STALE'))

# ── 4. prior-month restatement ──────────────────────────────────────────
if prev:
    print('\n  PRIOR-MONTH RESTATEMENT  (against the %s build)' % prev.get('cycleLabel', 'previous'))
    a, b = prev.get('MONTHLY', []), meta.get('MONTHLY', [])
    THRESH = 50000
    moved = False
    for i in range(min(len(a), len(b))):
        d = b[i] - a[i]
        if abs(d) >= THRESH:
            moved = True
            mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
                   'Oct', 'Nov', 'Dec'][i]
            warns.append('%s restated by %s since the previous build'
                         % (mon, format(d, ',')))
            print('    %-4s %14s -> %14s   %+15s   RESTATED'
                  % (mon, format(a[i], ','), format(b[i], ','), format(d, ',')))
    if len(b) > len(a):
        print('    %d new month(s) added' % (len(b) - len(a)))
    if not moved:
        print('    no month moved by more than %s' % format(THRESH, ','))
else:
    print('\n  PRIOR-MONTH RESTATEMENT  skipped, no previous build_meta given')

# ── result ──────────────────────────────────────────────────────────────
print('\n' + '=' * 62)
if warns:
    print('WARNINGS (%d)' % len(warns))
    for w in warns:
        print('  warn  %s' % w)
if fails:
    print('FAILURES (%d) - do not publish' % len(fails))
    for f in fails:
        print('  FAIL  %s' % f)
    sys.exit(1)
print('RECONCILIATION PASSED')
