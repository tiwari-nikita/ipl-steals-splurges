"""Fair value line: what each player's season was worth at the league's own going rate per run.

- Replacement level = how a minimum-price player performs (runs added per ball involved, for players
  paid at most 0.5 crore who were involved in 120+ balls).
- Runs above replacement (RAR) = runs added - replacement rate x balls involved (faced + bowled).
- Going rate = money teams spent above the minimum salary / total positive RAR.
- Fair price = minimum salary + going rate x max(RAR, 0). Gap = salary - fair price.
Withdrawn (injured/unavailable) players are excluded; players who never played are listed separately.
Usage: python -I pipeline/05_fair_value.py <out_dir> <season> <site_data_json>
"""
import json
import os
import sys

import numpy as np
import pandas as pd

out, season, site_json = sys.argv[1], int(sys.argv[2]), sys.argv[3]
MIN_SAL = 0.30  # crore, IPL minimum
pl = pd.read_csv(os.path.join(out, f"players_{season}.csv"))
pl["withdrawn"] = pl["withdrawn"].astype(str).str.lower().eq("true")
pl["involvement"] = pl.balls_faced + pl.balls_bowled

pool = pl[~pl.withdrawn].copy()
cheap = pool[(pool.salary_cr <= 0.5) & (pool.involvement >= 120)]
repl_rate = cheap.runs_added.sum() / cheap.involvement.sum()
pool["rar"] = pool.runs_added - repl_rate * pool.involvement
paid_above_min = (pool.salary_cr - MIN_SAL).clip(lower=0).sum()
rate_cr = paid_above_min / pool.rar.clip(lower=0).sum()           # crore per run above replacement
pool["fair_cr"] = MIN_SAL + rate_cr * pool.rar.clip(lower=0)
pool["gap_cr"] = pool.salary_cr - pool.fair_cr


def role(r):
    if r.balls_faced >= 60 and r.balls_bowled >= 60:
        return "All-rounder"
    if r.balls_bowled > r.balls_faced:
        return "Bowler"
    return "Batter"


pool["role"] = [role(r) for r in pool.itertuples()]
played = pool[pool.matches > 0].copy()
benched = pool[pool.matches == 0].copy()
regulars = played[played.matches >= 5]

teams = pool.groupby("team").agg(spend_cr=("salary_cr", "sum"), rar=("rar", lambda s: s.clip(lower=0).sum()),
                                 fair_cr=("fair_cr", "sum")).reset_index()
teams["value_per_cr"] = teams.rar / teams.spend_cr
teams = teams.sort_values("value_per_cr", ascending=False)

pool.to_csv(os.path.join(out, f"fair_value_{season}.csv"), index=False)

players = []
for r in played.sort_values("gap_cr").itertuples():
    players.append({"name": r.player, "team": r.team, "role": r.role, "salary": round(r.salary_cr, 2),
                    "fair": round(r.fair_cr, 2), "gap": round(r.gap_cr, 2), "matches": int(r.matches),
                    "runs": int(r.runs), "wickets": int(r.wickets), "runs_added": round(r.runs_added, 1),
                    "rar": round(r.rar, 1), "source": r.source})
data = {
    "season": season,
    "rate_lakh_per_run": round(rate_cr * 100, 2),
    "replacement_rate_per_100_balls": round(repl_rate * 100, 2),
    "players": players,
    "benched": [{"name": r.player, "team": r.team, "salary": round(r.salary_cr, 2)} for r in benched.sort_values("salary_cr", ascending=False).itertuples()],
    "teams": [{"team": r.team, "spend": round(r.spend_cr, 2), "rar": round(r.rar, 1), "value_per_cr": round(r.value_per_cr, 2)} for r in teams.itertuples()],
}
os.makedirs(os.path.dirname(site_json), exist_ok=True)
json.dump(data, open(site_json, "w"), indent=1)

print(f"replacement level: {repl_rate*100:.2f} runs added per 100 balls (from {len(cheap)} min-price regulars)")
print(f"going rate: {rate_cr*100:.2f} lakh per run above replacement | pool {len(pool)} | played {len(played)} | benched {len(benched)}")
cols = ["player", "team", "role", "salary_cr", "fair_cr", "gap_cr", "matches", "runs", "wickets", "rar"]
print("\nSTEALS (regulars):"); print(regulars.sort_values("gap_cr").head(10)[cols].round(2).to_string(index=False))
print("\nSPLURGES (regulars):"); print(regulars.sort_values("gap_cr", ascending=False).head(10)[cols].round(2).to_string(index=False))
print("\nBENCHED (paid, no match):"); print(benched.sort_values("salary_cr", ascending=False).head(6)[["player", "team", "salary_cr"]].to_string(index=False))
print("\nTEAMS:"); print(teams.round(2).to_string(index=False))
