"""Flatten Cricsheet IPL JSON into one row per delivery, plus one row per player per match.

Usage: python -I pipeline/01_deliveries.py <cricsheet_json_dir> <out_dir>
"""
import json
import os
import sys

import pandas as pd

src, out = sys.argv[1], sys.argv[2]
rows, apps = [], []
for f in sorted(os.listdir(src)):
    if not f.endswith(".json"):
        continue
    m = json.load(open(os.path.join(src, f)))
    info = m["info"]
    mid = f[:-5]
    season = str(info.get("season"))
    reg = info.get("registry", {}).get("people", {})
    for team, players in info.get("players", {}).items():
        for p in players:
            apps.append({"match_id": mid, "season": season, "team": team, "player": p, "player_id": reg.get(p)})
    teams = list(info.get("players", {}).keys())
    for inn_no, inn in enumerate(m.get("innings", []), start=1):
        if inn.get("super_over"):
            continue
        bat = inn["team"]
        bowl = next((t for t in teams if t != bat), None)
        legal = 0
        wkts = 0
        for ov in inn.get("overs", []):
            for d in ov.get("deliveries", []):
                ex = d.get("extras", {})
                wide, nb = ex.get("wides", 0), ex.get("noballs", 0)
                is_legal = not (wide or nb)
                wk = d.get("wickets", [])
                rows.append({
                    "match_id": mid, "season": season, "innings": inn_no, "bat_team": bat, "bowl_team": bowl,
                    "over": ov["over"], "legal_before": legal, "wkts_before": wkts,
                    "batter": d["batter"], "batter_id": reg.get(d["batter"]),
                    "bowler": d["bowler"], "bowler_id": reg.get(d["bowler"]),
                    "runs_batter": d["runs"]["batter"], "runs_extras": d["runs"]["extras"], "runs_total": d["runs"]["total"],
                    "wides": wide, "noballs": nb, "byes": ex.get("byes", 0), "legbyes": ex.get("legbyes", 0),
                    "is_legal": is_legal,
                    "wicket": len(wk) > 0,
                    "player_out": wk[0]["player_out"] if wk else None,
                    "player_out_id": reg.get(wk[0]["player_out"]) if wk else None,
                    "wicket_kind": wk[0]["kind"] if wk else None,
                })
                legal += 1 if is_legal else 0
                wkts += len(wk)

dl = pd.DataFrame(rows)
ap = pd.DataFrame(apps)
os.makedirs(out, exist_ok=True)
dl.to_pickle(os.path.join(out, "deliveries.pkl"))
ap.to_pickle(os.path.join(out, "appearances.pkl"))
print("deliveries", len(dl), "matches", dl.match_id.nunique(), "appearances", len(ap))
print(dl.groupby("season").match_id.nunique().tail(6).to_dict())
