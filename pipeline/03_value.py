"""Runs Added: how many runs each player added compared with an average player in the same match situation.

1. Expected-runs table ER[balls_left, wickets_lost] from first innings, Impact Player era (2023+).
2. Every delivery's run value = runs scored + ER(after) - ER(before).
3. Batter gets the runs off the bat plus the change in expectation from using up a ball; whoever is out
   carries the wicket's cost. Bowler gets the opposite of runs charged to them and the ball's change, plus
   the wicket's value only for bowler-credited dismissals (not run-outs).
Usage: python -I pipeline/03_value.py <out_dir>
"""
import os
import sys

import numpy as np
import pandas as pd

out = sys.argv[1]
dl = pd.read_pickle(os.path.join(out, "deliveries.pkl"))
ap = pd.read_pickle(os.path.join(out, "appearances.pkl"))
dl["season_i"] = dl.season.str[:4].astype(int)
ap["season_i"] = ap.season.str[:4].astype(int)

# ---- 1. expected remaining runs table (first innings, 2023-2026) ----
fi = dl[(dl.innings == 1) & (dl.season_i >= 2023)].copy()
fi["runs_before"] = fi.groupby("match_id").runs_total.cumsum() - fi.runs_total
fi["inn_total"] = fi.groupby("match_id").runs_total.transform("sum")
fi["remaining"] = fi.inn_total - fi.runs_before
leg = fi[fi.is_legal]
grid = leg.groupby(["legal_before", "wkts_before"]).remaining.agg(["mean", "size"]).reset_index()

ER = np.full((121, 11), np.nan)
for _, r in grid.iterrows():
    if r["size"] >= 30:
        ER[int(r.legal_before), int(r.wkts_before)] = r["mean"]
ER[120, :] = 0.0
ER[:, 10] = 0.0
# fill sparse cells: along wickets use the median ratio to the previous wicket count at the same ball
for w in range(1, 10):
    with np.errstate(invalid="ignore", divide="ignore"):
        ratios = ER[:120, w] / ER[:120, w - 1]
    finite = ratios[np.isfinite(ratios)]
    rmed = float(np.median(finite)) if finite.size else 0.85
    for b in range(120):
        if np.isnan(ER[b, w]) and not np.isnan(ER[b, w - 1]):
            ER[b, w] = ER[b, w - 1] * rmed
# anything still empty at 0 wickets: interpolate along balls
for w in range(10):
    col = pd.Series(ER[:121, w])
    ER[:121, w] = col.interpolate(limit_direction="both").to_numpy()
# expectations can only fall as balls are used: enforce monotone non-increasing along balls
for w in range(11):
    ER[:, w] = np.minimum.accumulate(ER[:, w])

# ---- 2. run value of every delivery ----
lb = dl.legal_before.clip(0, 120).to_numpy()
wb = dl.wkts_before.clip(0, 10).to_numpy()
legal = dl.is_legal.to_numpy()
wk = dl.wicket.to_numpy()
la = np.where(legal, np.minimum(lb + 1, 120), lb)
wa = np.minimum(wb + wk.astype(int), 10)
er_before = ER[lb, wb]
er_after_nowk = ER[la, wb]
er_after = ER[la, wa]
base_delta = er_after_nowk - er_before          # cost/credit of using the ball
wk_delta = er_after - er_after_nowk             # extra cost of the wicket (<= 0)

BOWLER_KINDS = {"bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"}
bowler_wk = dl.wicket_kind.isin(BOWLER_KINDS).to_numpy()
faced = ~(dl.wides.to_numpy() > 0)              # wides are not faced by the batter
bowler_runs = dl.runs_batter.to_numpy() + dl.wides.to_numpy() + dl.noballs.to_numpy()

dl["bat_rv"] = np.where(faced, dl.runs_batter.to_numpy() + base_delta, 0.0)
dl["bowl_rv"] = -(bowler_runs + base_delta) - np.where(bowler_wk, wk_delta, 0.0)
dl["out_rv"] = np.where(wk, wk_delta, 0.0)       # charged to whoever was out

# ---- 3. season totals per player ----
dl["faced"] = dl.wides == 0                      # wides are not balls faced
bat = dl.groupby(["season_i", "batter_id"]).agg(bat_runs_added=("bat_rv", "sum"), runs=("runs_batter", "sum"),
                                                 balls_faced=("faced", "sum")).reset_index().rename(columns={"batter_id": "pid"})
outs = dl[dl.wicket].groupby(["season_i", "player_out_id"]).agg(out_cost=("out_rv", "sum"), dismissals=("out_rv", "size")).reset_index().rename(columns={"player_out_id": "pid"})
bowl = dl.groupby(["season_i", "bowler_id"]).agg(bowl_runs_added=("bowl_rv", "sum"), balls_bowled=("is_legal", "sum"),
                                                  runs_conceded=("runs_total", "sum")).reset_index().rename(columns={"bowler_id": "pid"})
wkts = dl[dl.wicket & dl.wicket_kind.isin(BOWLER_KINDS)].groupby(["season_i", "bowler_id"]).size().rename("wickets").reset_index().rename(columns={"bowler_id": "pid"})
games = ap.groupby(["season_i", "player_id"]).agg(matches=("match_id", "nunique"), name=("player", "last"),
                                                   team=("team", "last")).reset_index().rename(columns={"player_id": "pid"})

pv = games.merge(bat, on=["season_i", "pid"], how="left").merge(outs, on=["season_i", "pid"], how="left") \
          .merge(bowl, on=["season_i", "pid"], how="left").merge(wkts, on=["season_i", "pid"], how="left")
pv = pv.fillna({c: 0 for c in ["bat_runs_added", "runs", "balls_faced", "out_cost", "dismissals",
                               "bowl_runs_added", "balls_bowled", "runs_conceded", "wickets"]})
pv["batting_raw"] = pv.bat_runs_added + pv.out_cost
pv["bowling_raw"] = pv.bowl_runs_added
# centre each season so the average ball faced / bowled is worth 0 that season (scoring levels change year to year)
seas = pv.groupby("season_i").agg(bf=("balls_faced", "sum"), bb=("balls_bowled", "sum"),
                                  bat=("batting_raw", "sum"), bowl=("bowling_raw", "sum"))
pv = pv.merge((seas.bat / seas.bf).rename("bat_pb"), left_on="season_i", right_index=True) \
       .merge((seas.bowl / seas.bb).rename("bowl_pb"), left_on="season_i", right_index=True)
pv["batting_added"] = pv.batting_raw - pv.balls_faced * pv.bat_pb
pv["bowling_added"] = pv.bowling_raw - pv.balls_bowled * pv.bowl_pb
pv["runs_added"] = pv.batting_added + pv.bowling_added
pv.to_csv(os.path.join(out, "player_value_by_season.csv"), index=False)
np.save(os.path.join(out, "expected_runs.npy"), ER)

# ---- sanity prints ----
print("ER at start (0 balls, 0 wkts):", round(ER[0, 0], 1), "| after 60 balls 2 wkts:", round(ER[60, 2], 1),
      "| 114 balls 9 wkts:", round(ER[114, 9], 1))
s26 = dl[dl.season_i == 2026]
c26 = pv[pv.season_i == 2026]
print("2026 centred totals (should be ~0): batting", round(c26.batting_added.sum(), 3), "bowling", round(c26.bowling_added.sum(), 3))
top = pv[pv.season_i == 2026].sort_values("runs_added", ascending=False)
print(top[["name", "team", "matches", "runs", "wickets", "batting_added", "bowling_added", "runs_added"]].head(12).round(1).to_string(index=False))
print("bottom:")
print(top[["name", "team", "matches", "runs", "wickets", "runs_added"]].tail(5).round(1).to_string(index=False))
