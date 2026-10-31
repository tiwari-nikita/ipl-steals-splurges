"""Build each player's IPL salary for a season from Wikipedia's 'List of <year> IPL personnel changes'.

Retained-player tables (No. / Player / Nationality / Salary) give the salary of everyone kept or traded in;
the auction tables (Auctioned price, in lakhs) give everyone bought at that year's auction.
Usage: python -I pipeline/02_salaries.py <personnel_<year>.json> <year> <out_csv>
"""
import io
import json
import re
import sys

import pandas as pd
from lxml import html as LH

src, year, out = sys.argv[1], sys.argv[2], sys.argv[3]
TEAMS = ["Chennai Super Kings", "Delhi Capitals", "Gujarat Titans", "Kolkata Knight Riders", "Lucknow Super Giants",
         "Mumbai Indians", "Punjab Kings", "Rajasthan Royals", "Royal Challengers Bengaluru", "Sunrisers Hyderabad"]

doc = LH.fromstring(json.load(open(src))["parse"]["text"])


def crore(s):
    """'₹18 crore (US$1.9 million)' -> 18.0 ; '₹30 lakh (...)' -> 0.30"""
    s = str(s).replace(",", "")
    m = re.search(r"₹\s*([\d.]+)\s*(crore|lakh)", s)
    if not m:
        return None
    v = float(m.group(1))
    return v if m.group(2) == "crore" else v / 100


def clean(name):
    return re.sub(r"\[.*?\]|\(.*?\)|†|‡|\*", "", str(name)).strip()


rows = []
# 1) retained tables: header Player + Salary; team = nearest preceding team name in document order
for t in doc.iter("table"):
    if t.xpath(".//table"):
        continue  # skip layout wrappers that hold the per-team tables
    head = " ".join(th.text_content().strip() for th in t.xpath("./tr[1]/th | ./tbody/tr[1]/th | ./thead/tr[1]/th"))
    if "Player" in head and "Salary" in head and "Nationality" in head:
        cap = " ".join(c.text_content() for c in t.xpath("./caption"))
        hits = [tm for tm in TEAMS if tm in cap]
        team = hits[0] if hits else None
        for el in ([] if team else t.itersiblings(preceding=True)):
            txt = el.text_content()
            hits = [tm for tm in TEAMS if tm in txt]
            if hits:
                team = hits[-1]
                break
        if team is None:  # fall back to the closest ancestor cell text before this table
            anc = t.getparent()
            while anc is not None and team is None:
                pre = "".join(x.text_content() for x in anc.itersiblings(preceding=True))
                hits = [tm for tm in TEAMS if tm in (anc.text or "") + pre[-200:]]
                team = hits[-1] if hits else None
                anc = anc.getparent()
        df = pd.read_html(io.StringIO(LH.tostring(t, encoding="unicode")))[0]
        for _, r in df.iterrows():
            rows.append({"player": clean(r["Player"]), "team": team, "nationality": r["Nationality"],
                         "salary_cr": crore(r["Salary"]), "source": "retained"})

# 2) auction sold tables
tabs = pd.read_html(io.StringIO(LH.tostring(doc, encoding="unicode")))
team_col = f"{year} IPL team"
for df in tabs:
    cols = [str(c) for c in df.columns]
    if team_col in cols and any(c.startswith("Auctioned price") for c in cols):
        pc = next(c for c in df.columns if str(c).startswith("Auctioned price"))
        for _, r in df.iterrows():
            team = str(r[team_col])
            price = pd.to_numeric(str(r[pc]).replace(",", ""), errors="coerce")
            if team in TEAMS and pd.notna(price):
                rows.append({"player": clean(r["Name"]), "team": team, "nationality": r.get("Country"),
                             "salary_cr": float(price) / 100, "source": "auction", "role": r.get("Role")})

# 3) withdrawn players and their replacements (signed mid-season)
withdrawn = set()
for df in tabs:
    cols = [str(c) for c in df.columns]
    if "Replacement player" in cols and "Team" in cols:
        rp_col = next(c for c in df.columns if str(c).startswith("Replacement player's price"))
        for _, r in df.iterrows():
            team = str(r["Team"])
            if team not in TEAMS:
                continue
            withdrawn.add((clean(r["Player"]), team))
            rep = clean(r["Replacement player"])
            price = crore(r[rp_col])
            if rep and rep.lower() not in ("nan", "none", "—", "-") and price is not None:
                rows.append({"player": rep, "team": team, "nationality": None, "salary_cr": price, "source": "replacement"})

sal = pd.DataFrame(rows)
sal = sal.dropna(subset=["salary_cr"])
sal = sal.drop_duplicates(subset=["player", "team"], keep="last")
sal["season"] = year
sal["withdrawn"] = [(p, t) in withdrawn for p, t in zip(sal.player, sal.team)]
sal.to_csv(out, index=False)
print("players", len(sal), "| by source", sal.source.value_counts().to_dict())
print(sal.groupby("team").agg(n=("player", "size"), spend_cr=("salary_cr", "sum")).round(2).to_string())
print("missing team:", int(sal.team.isna().sum()))
