"""Rebuild-free checks on everything the site publishes. Run after the pipeline:
    .venv/bin/python -I verify.py <project_dir>
Exits non-zero if any check fails.
"""
import io
import json
import os
import sys
from collections import defaultdict

import pandas as pd

P = sys.argv[1]
out, raw = os.path.join(P, "out"), os.path.join(P, "data", "raw")
site = json.load(open(os.path.join(P, "site", "data", "season_2026.json")))
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)


dl = pd.read_pickle(os.path.join(out, "deliveries.pkl"))
pv = pd.read_csv(os.path.join(out, "player_value_by_season.csv"))
sal = pd.read_csv(os.path.join(out, "salaries_2026.csv"))
fv = pd.read_csv(os.path.join(out, "fair_value_2026.csv"))

# 1. coverage
check("2026 has all 74 matches", dl[dl.season == "2026"].match_id.nunique() == 74)
core = sal[sal.source.isin(["retained", "auction"])]
check("250 contracted players, 25 per team", len(core) == 250 and core.groupby("team").size().eq(25).all())
check("173 retained + 77 bought (matches Wikipedia summary)", (core.source == "retained").sum() == 173 and (core.source == "auction").sum() == 77)

# 2. cross-check season leaders against Wikipedia's 2026 season page
h = json.load(open(os.path.join(raw, "wiki", "season_2026.json")))["parse"]["text"]
tabs = pd.read_html(io.StringIO(h))
runs_tab = next(t for t in tabs if list(t.columns)[:2] == ["Runs", "Player"])
wk_tab = next(t for t in tabs if list(t.columns)[:2] == ["Wickets", "Player"])
p26 = pv[pv.season_i == 2026]
check("top-5 run totals match Wikipedia", sorted(runs_tab.Runs.head(5)) == sorted(p26.runs.nlargest(5).astype(int)),
      f"{list(runs_tab.Runs.head(5))}")
check("top-5 wicket totals match Wikipedia", sorted(wk_tab.Wickets.head(5)) == sorted(p26.wickets.nlargest(5).astype(int)),
      f"{list(wk_tab.Wickets.head(5))}")

# 3. independent recompute of one player's runs scored and balls faced with a plain loop
name = "V Suryavanshi"
r = b = 0
for row in dl[(dl.season == "2026") & (dl.batter == name)].itertuples():
    r += row.runs_batter
    b += 0 if row.wides else 1
pr = p26[p26.name == name].iloc[0]
check(f"{name}: runs and balls faced recomputed", r == pr.runs and b == pr.balls_faced, f"{r} runs, {b} balls")

# 4. season centring: average player adds ~0 in 2026
check("2026 runs added centred on zero", abs(p26.batting_added.sum()) < 1e-6 and abs(p26.bowling_added.sum()) < 1e-6)

# 5. fair value arithmetic
pool = fv[~fv.withdrawn.astype(str).str.lower().eq("true")]
rate = (pool.salary_cr - 0.30).clip(lower=0).sum() / pool.rar.clip(lower=0).sum()
check("going rate reproduces", abs(rate * 100 - site["rate_lakh_per_run"]) < 0.01, f"{rate*100:.2f} lakh per run")
check("value delivered sums to money spent (league-wide)", abs(pool.fair_cr.sum() - pool.salary_cr.sum()) < 0.01,
      f"{pool.fair_cr.sum():.2f} vs {pool.salary_cr.sum():.2f} cr")
bad = [p for p in site["players"] if abs(p["salary"] - p["fair"] - p["gap"]) > 0.011]
check("every published gap = paid - value", not bad, f"{len(bad)} mismatches")
wd = set(sal[sal.withdrawn].player)
check("no withdrawn/injured player is ranked", not any(p["name"] in wd for p in site["players"]))
check("'paid, didn't play' list really has 0 matches", all(fv[fv.player == b["name"]].matches.eq(0).all() for b in site["benched"]))

# 6. team totals
tsum = defaultdict(float)
for p in pool.itertuples():
    tsum[p.team] += p.salary_cr
check("team spend in table matches player rows", all(abs(t["spend"] - tsum[t["team"]]) < 0.01 for t in site["teams"]))

print(f"\n{len(fails)} failed" if fails else "\nALL CHECKS PASSED")
sys.exit(1 if fails else 0)
