# Scorecard CI — what to add to the repo

Drop these four paths into `PacTeamAmerica/pac-team-scorecard` on `main`:

```
.github/workflows/scorecard-ci.yml
test/deeprender.js
test/verify_stale.py
test/verify_revtiming.py
build_meta.json
```

Nothing else changes. `index.html` and `snapshot-history.json` stay exactly where
they are. There is no `package.json` and no install step — the harness stubs React,
ReactDOM, SheetJS and Chart.js itself, and the two Python gates use only the standard
library. CI cannot go red because of a registry outage or a dependency bump.

## Why each gate exists

Every one of these was written after the bug it catches reached the live page.

| Gate | The bug it exists for |
|---|---|
| `test/deeprender.js` | **3 Aug 2026.** A one-word typo inside a component body (`score` for `total`) shipped and blanked the entire page, while every check at the time passed. Component bodies below `App()` don't execute under a shallow mock. |
| `test/verify_stale.py` | **19 + 25 Oct 2026.** `invMeta.net` sat in a `useState` default rather than a named seed, so it survived two rebuilds at the 13 Oct value and understated Revenue YTD by **$1,041,205** on a CEO-facing page. |
| `test/verify_revtiming.py` | **27 Oct 2026.** Every booked open order was assigned to the current year, overstating the 2026 projection by **$4.5M–$5.3M** for two builds. Caught by the controller from the NetSuite side, not by this file. |

## What they check

**`deeprender.js`** discovers the tab bar from the HTML itself, so it works on the
2-tab live build, the 7-tab re-cut, and anything added later without being edited.
Per tab it asserts the whole `createElement` tree builds with zero throws, and that
every tab button has a matching render line in the source — a button wired to nothing
produces a blank tab, which is the same class of bug as the typo.

**`verify_stale.py`** asserts `invMeta.net` equals the sum of `MONTHLY_2026`, that the
three active-client figures match the SuiteQL pull, and that no rendered string
anywhere carries a date from a prior cycle. Code comments are skipped on purpose —
they hold legitimate historical provenance.

**`verify_revtiming.py`** asserts the 2026 / 2027 / undated bands reconcile to the
open-order total, that the 2027 band is non-zero (a zero means the model has been lost
again), and — the hard gate — that **booked + dated does not exceed the seasonal model's
high by more than $1M**. Three independent projections live in this file and they were
previously allowed to disagree silently; this makes that fatal.

## Verified behaviour

Each gate was run against a reconstruction of the build that contained its bug:

| Gate | Against the broken build | Against the current build |
|---|---|---|
| `deeprender.js` | fails on an unwired tab button, exit 1 | 2/2 and 7/7 tabs clean, exit 0 |
| `verify_stale.py` | fails on `net:12889347` and 8 stale date labels | passes |
| `verify_revtiming.py` | fails at **+$3,286,333 over the seasonal high** | passes |

## One thing to know about `build_meta.json`

It is the record of what the rebuild computed, and the gates assert the HTML agrees
with it. **Both files must be committed together.** A commit that updates `index.html`
without `build_meta.json` will go red, which is intended — it means a partial rebuild
shipped.

## A deliberate non-gate

`verify_revtiming.py` reports the flat run-rate projection but does **not** gate on it.
PAC TEAM is back-half heavy — August and December alone were 42% of 2025 revenue — so
extrapolating the remaining weeks at the year-to-date average structurally understates
the year end. A booked figure above a flat run-rate is evidence of seasonality, not of
error, and gating on it would only generate false alarms. The seasonal model is the
correct comparator and catches the error class on its own.

This is written down so that a future reader does not mistake it for the gate having
been weakened to get a green light. If you ever need to widen a limit to make CI pass,
treat that as a finding rather than a chore.
