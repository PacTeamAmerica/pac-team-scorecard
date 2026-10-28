#!/usr/bin/env python3
"""Revenue-timing reconciliation gate for the PAC TEAM Commercial Scorecard.

Added 28 Oct 2026, approved by Joseph, after the multi-release program error.

The error that prompted this was visible for weeks and nothing was watching it:
the scorecard's booked-and-landing projection sat ~$3.4M ABOVE its own seasonal
model and ~$5.7M above its own run-rate extrapolation, because it assigned every
booked open order to the current year. Three independent methods live in the
same file and they were allowed to disagree silently.

This gate makes that disagreement fatal. Run it at every rebuild:

    python3 -I verify_revtiming.py <build>.html build_meta.json

Exit 0 = ship. Exit 1 = do not ship.
"""
import re, sys, json

GATE = 1_000_000   # dollars of unexplained divergence that blocks a ship

f, metaf = sys.argv[1], sys.argv[2]
s = open(f, encoding='utf8').read()
meta = json.load(open(metaf))
fails, warns = [], []


def money(v):
    return '$' + format(int(round(v)), ',')


def grab(pat, label, cast=float):
    m = re.search(pat, s)
    if not m:
        fails.append('could not find ' + label)
        return None
    return cast(m.group(1))


print('REVENUE TIMING RECONCILIATION  ' + f)

# ── the dated open book ───────────────────────────────────────────────────
openTot  = grab(r"REVTIMING_SEED\s*=\s*\{[^}]*?openTot:(\d+)", 'openTot')
b27lo    = grab(r"bklg27Lo:(\d+)", 'bklg27Lo')
b27hi    = grab(r"bklg27Hi:(\d+)", 'bklg27Hi')
undated  = grab(r"undated:(\d+)", 'undated')
if None in (openTot, b27lo, b27hi, undated):
    print('\nFAILURES: ' + '; '.join(fails)); sys.exit(1)

print('\n  open book            ' + money(openTot).rjust(14))
print('  2027 booked backlog  ' + (money(b27lo) + ' - ' + money(b27hi)).rjust(14))
print('  no invoicing date    ' + money(undated).rjust(14))

open26lo = openTot - b27hi - undated
open26hi = openTot - b27lo - undated
print('  bills in 2026        ' + (money(open26lo) + ' - ' + money(open26hi)).rjust(14))


def chk(name, ok, detail=''):
    print(('  ok    ' if ok else '  FAIL  ') + name + (('   ' + detail) if detail else ''))
    if not ok:
        fails.append(name)


chk('bands reconcile to the open book',
    abs((open26lo + b27hi + undated) - openTot) < 2 and
    abs((open26hi + b27lo + undated) - openTot) < 2)
chk('2027 band is ordered and non-zero', 0 < b27lo <= b27hi)
chk('2026 slice is non-negative', open26lo >= 0)

# ── the three projections ────────────────────────────────────────────────
rev = meta['net']
MONTHLY = re.search(r'MONTHLY_2026\s*=\s*\[([^\]]*)\]', s).group(1)
months = [int(x) for x in MONTHLY.split(',')]
chk('MONTHLY_2026 sums to revenue YTD', sum(months) == rev,
    money(sum(months)) + ' vs ' + money(rev))

SEAS = re.search(r'SEASONAL_2025\s*=\s*\[([^\]]*)\]', s)
pipeLanding = meta.get('pipeLanding', 0)
booked_lo = rev + open26lo + pipeLanding
booked_hi = rev + open26hi + pipeLanding
booked_mid = (booked_lo + booked_hi) / 2

print('\n  METHOD COMPARISON')
print('    booked + dated       ' + (money(booked_lo) + ' - ' + money(booked_hi)).rjust(26))

seas_lo = seas_hi = None
if SEAS:
    seasonal = [float(x) for x in SEAS.group(1).split(',')]
    tot25 = sum(seasonal)
    # day-prorated share of 2025 revenue recognised by the as-of date
    m = re.search(r"YTD_ASOF\s*=\s*\{label:'[^']*',\s*month:(\d+),\s*dayFrac:(\d+)/(\d+)", s)
    if m:
        mi, dnum, dden = int(m.group(1)), float(m.group(2)), float(m.group(3))
        cum = sum(seasonal[:mi]) + seasonal[mi] * (dnum / dden)
        share = cum / tot25
        seas_lo = rev + (tot25 - cum)
        seas_hi = rev / share if share > 0.02 else seas_lo
        print('    seasonal model       ' + (money(seas_lo) + ' - ' + money(seas_hi)).rjust(26))
    else:
        warns.append('could not parse YTD_ASOF; seasonal check skipped')
else:
    warns.append('SEASONAL_2025 not found; seasonal check skipped')

# run-rate extrapolation off the trailing weeks
runrate = meta.get('runRateWeekly')
if runrate is None:
    # fall back to TTM/52 if the rebuild recorded it, else derive from the year so far
    import datetime
    asof = datetime.date(2026, 10, 25)
    weeks_elapsed = (asof - datetime.date(2026, 1, 1)).days / 7.0
    runrate = rev / weeks_elapsed
weeks_left = 9.5
run_land = rev + runrate * weeks_left
print('    run-rate extrapolation' + money(run_land).rjust(25))

# ── THE GATE ─────────────────────────────────────────────────────────────
# The failure mode was the booked projection floating ABOVE every other method.
# A booked figure below the seasonal model is normal and expected late in the
# year (unbooked December business), so that direction only warns.
print('\n  GATE  (booked projection vs the other two methods, limit ' + money(GATE) + ')')
if seas_hi is not None:
    over_seasonal = booked_mid - seas_hi
    chk('booked + dated does not float above the seasonal model',
        over_seasonal <= GATE,
        ('+' + money(over_seasonal) + ' over seasonal high') if over_seasonal > 0
        else (money(-over_seasonal) + ' below seasonal high'))
    if booked_lo < seas_lo - GATE:
        warns.append('booked + dated sits ' + money(seas_lo - booked_lo) +
                     ' below the seasonal low. Expected late in the year when December '
                     'business is not yet booked, but confirm quote volume supports it.')

# The flat run-rate is INFORMATIONAL, not a gate, and deliberately so - this is
# not the gate being loosened to get a green light. PAC TEAM is back-half heavy
# (Aug + Dec alone were 42% of 2025 revenue), so projecting the remaining weeks
# at the year-to-date average structurally understates the year end. A booked
# figure above a flat run-rate is evidence of seasonality, not of error.
# The seasonal model is the correct comparator and is the hard gate above: run
# against the 25 Oct build as it shipped, booked + landing was $23,290,660 vs a
# seasonal high of $20,000,326, i.e. +$3,290,334 - caught, and caught by the
# seasonal check alone. Widening to two hard gates would only add false alarms.
over_run = booked_mid - run_land
print('    (flat run-rate is seasonally biased low; shown for context, not gated: '
      + (('+' + money(over_run) + ' over') if over_run > 0 else (money(-over_run) + ' under'))
      + ')')
if over_run > 4 * GATE:
    warns.append('booked + dated is ' + money(over_run) + ' above even the flat run rate. '
                 'Seasonality explains perhaps $1-2M of that; a gap this wide needs a reason '
                 'before the file ships.')

# ── the label that was wrong ─────────────────────────────────────────────
print('\n  LABEL CHECK')
# Only RENDERED LABELS matter here. Prose and code comments that describe the
# 28 Oct correction necessarily contain the old phrase, and scrubbing them would
# erase the audit trail - so the check looks at label elements specifically:
# className:'l'/'r-lbl'/'fb-lbl'/'s-lbl' followed immediately by the string.
labels = re.findall(r"className:'(?:l|r-lbl|fb-lbl|s-lbl|tile-lbl)'\},\s*'([^']*)'", s)
bad = [l for l in labels if re.fullmatch(r'\s*2027 backlog\s*', l)]
chk('no rendered label is a bare "2027 backlog"', not bad,
    repr(bad[:3]) if bad else str(len(labels)) + ' labels scanned')
chk('the pipeline residual is labelled as pipeline',
    'Pipeline not landing in 2026' in s)
chk('booked 2027 backlog band is present',
    '2027 booked backlog' in s)

print()
for w in warns:
    print('  warn  ' + w)
print('\n' + ('REVENUE TIMING PASSED' if not fails
             else 'DO NOT SHIP - ' + str(len(fails)) + ' failure(s): ' + '; '.join(fails)))
sys.exit(1 if fails else 0)
