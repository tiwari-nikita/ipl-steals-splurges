"""Join Wikipedia salary names (full names) to Cricsheet player IDs (scorecard names like 'RD Gaikwad').

Match within the same franchise first, by surname + first initial, then by any shared name token;
anything still unmatched is resolved by data/manual_name_map.csv (wiki_name,team,cricsheet_name).
Players with no 2026 appearance are kept with 0 matches (paid but didn't play).
Usage: python -I pipeline/04_match.py <out_dir> <manual_map_csv> <season>
"""
import os
import re
import sys
import unicodedata

import pandas as pd

out, manual_csv, season = sys.argv[1], sys.argv[2], int(sys.argv[3])
sal = pd.read_csv(os.path.join(out, f"salaries_{season}.csv"))
pv = pd.read_csv(os.path.join(out, "player_value_by_season.csv"))
ap = pd.read_pickle(os.path.join(out, "appearances.pkl"))


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).split()


cur = pv[pv.season_i == season][["pid", "name", "team"]]
# everyone who has ever played in the IPL, for players who changed team or didn't play this season
allp = ap.groupby("player_id").agg(name=("player", "last"), last_team=("team", "last")).reset_index().rename(columns={"player_id": "pid"})
manual = pd.read_csv(manual_csv) if os.path.exists(manual_csv) else pd.DataFrame(columns=["wiki_name", "team", "cricsheet_name"])
mmap = {(r.wiki_name, r.team): r.cricsheet_name for r in manual.itertuples()}


def score(wiki, cs):
    w, c = norm(wiki), norm(cs)
    if not w or not c:
        return 0
    if " ".join(w) == " ".join(c):
        return 100
    s = 0
    first_raw = str(cs).split()[0]
    cs_first_is_initials = first_raw.isupper() and len(first_raw) <= 4
    if w[-1] == c[-1]:
        s += 50
        if c[0][0] == w[0][0]:
            s += 30          # 'RD Gaikwad' vs 'Ruturaj Gaikwad'
        if not cs_first_is_initials and len(c) > 1 and c[0] != w[0] and c[0] not in w:
            s -= 40          # 'Ramandeep Singh' is not 'Rinku Singh'
    if set(w) <= set(c):
        s += 40              # 'Sai Sudharsan' inside 'B Sai Sudharsan'
    shared = set(w) & set(c)
    s += 10 * len(shared)
    return s


rows = []
used = set()
for r in sal.itertuples():
    pick, how = None, None
    if (r.player, r.team) in mmap:
        nm = mmap[(r.player, r.team)]
        hit = allp[allp.name == nm]
        if len(hit):
            pick, how = hit.iloc[0].pid, "manual"
        elif str(nm).upper() == "NONE":
            how = "manual-none"
    if pick is None and how is None:
        cands = cur[(cur.team == r.team) & ~cur.pid.isin(used)]
        best = max(((score(r.player, c.name), c.pid) for c in cands.itertuples()), default=(0, None))
        if best[0] >= 80:
            pick, how = best[1], "team"
        else:
            pool = allp[~allp.pid.isin(used)]
            scored = [(score(r.player, c.name), c.pid) for c in pool.itertuples()]
            best = max(scored, default=(0, None))
            strong = [x for x in scored if x[0] >= 80]
            if best[0] >= 100 or (best[0] >= 80 and len(strong) == 1):
                pick, how = best[1], "global"
    if pick is not None:
        used.add(pick)
    rows.append({**r._asdict(), "pid": pick, "match_how": how})

m = pd.DataFrame(rows).drop(columns=["Index"])
m = m.merge(allp[["pid", "name"]].rename(columns={"name": "cricsheet_name"}), on="pid", how="left")
vals = pv[pv.season_i == season][["pid", "matches", "runs", "wickets", "balls_faced", "balls_bowled",
                                   "batting_added", "bowling_added", "runs_added"]]
m = m.merge(vals, on="pid", how="left")
prev = pv[pv.season_i == season - 1][["pid", "runs_added", "matches"]].rename(columns={"runs_added": "runs_added_prev", "matches": "matches_prev"})
m = m.merge(prev, on="pid", how="left")
for c in ["matches", "runs", "wickets", "balls_faced", "balls_bowled", "batting_added", "bowling_added", "runs_added"]:
    m[c] = m[c].fillna(0)
m.to_csv(os.path.join(out, f"players_{season}.csv"), index=False)

print("salary rows", len(m), "| matched", int(m.pid.notna().sum()), "| by method", m.match_how.value_counts(dropna=False).to_dict())
dup = m[m.pid.notna() & m.pid.duplicated(keep=False)]
print("duplicate pid matches:", len(dup))
if len(dup):
    print(dup[["player", "team", "cricsheet_name"]].to_string(index=False))
un = m[m.pid.isna() & (m.match_how != "manual-none")]
print("unmatched:", len(un))
print(un[["player", "team", "salary_cr", "source"]].to_string(index=False))
