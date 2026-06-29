#!/usr/bin/env python3
"""Economically refresh odds + results for the WC2026 bracket.

Two cheap Odds-API calls (free-tier credits in brackets):
  - scores  GET /scores                      [1 credit]  -> results.json winners
  - odds    GET /odds  markets=h2h regions=eu [1 credit]  -> odds_market.json 1X2

Only the 16 tracked R32 fixtures are touched (deeper rounds are Elo-modelled,
not fetched). A played fixture leaves the odds feed but is kept in
odds_market.json and pinned in results.json. Once every fixture is decided the
odds call is skipped entirely, so spending tapers to ~1 credit/run and then 0.

Budget math: at ~2 credits/run, every 3 h (8 runs/day) ≈ 16 credits/day, well
within the 500/month free tier across the ~3-week knockout stage.

Usage:  ODDS_API_KEY=... python3 refresh.py
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SPORT = "soccer_fifa_world_cup"
BASE = f"https://api.the-odds-api.com/v4/sports/{SPORT}"
LAY_BOOKS = {"betfair_ex_eu", "betfair_ex_uk", "matchbook"}


def get(url):
    with urllib.request.urlopen(url, timeout=25) as r:
        print(f"  [API] remaining={r.headers.get('x-requests-remaining','?')} "
              f"cost={r.headers.get('x-requests-last','?')}", file=sys.stderr)
        return json.load(r)


def demargin(h, d, a):
    inv = [1 / h, 1 / d, 1 / a]
    s = sum(inv)
    return [x / s for x in inv]


def load(name, default):
    fp = HERE / name
    return json.loads(fp.read_text()) if fp.exists() else default


def main():
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        sys.exit("set ODDS_API_KEY")

    market = load("odds_market.json", {"matches": []})
    by_key = {(m["home"], m["away"]): m for m in market["matches"]}
    results = load("results.json", {})
    tracked = set(by_key)  # exactly the 16 R32 fixtures; never grow this

    changed = False

    # --- scores -> results.json -------------------------------------------
    try:
        scores = get(f"{BASE}/scores/?apiKey={key}")
    except Exception as e:  # noqa: BLE001
        scores = []
        print(f"scores fetch failed: {e}", file=sys.stderr)
    for e in scores:
        k = (e["home_team"], e["away_team"])
        if not e.get("completed") or k not in tracked:
            continue
        sc = {s["name"]: int(s["score"]) for s in (e.get("scores") or [])
              if s.get("score") is not None}
        h, a = k
        if h not in sc or a not in sc:
            continue
        if sc[h] == sc[a]:
            print(f"  level {h} {sc[h]}-{sc[a]} {a}: penalty winner unknown — "
                  f"set results.json manually", file=sys.stderr)
            continue
        winner = h if sc[h] > sc[a] else a
        rec = {"winner": winner, "score": f"{sc[h]}-{sc[a]}"}
        if results.get(f"{h}|{a}") != rec:
            results[f"{h}|{a}"] = rec
            changed = True
            print(f"  result: {h} {sc[h]}-{sc[a]} {a} -> {winner}", file=sys.stderr)

    # --- odds -> odds_market.json (skip once all decided) ------------------
    undecided = [k for k in tracked if f"{k[0]}|{k[1]}" not in results]
    if undecided:
        try:
            events = get(f"{BASE}/odds?apiKey={key}&regions=eu&markets=h2h&oddsFormat=decimal")
        except Exception as e:  # noqa: BLE001
            events = []
            print(f"odds fetch failed: {e}", file=sys.stderr)
        for e in events:
            k = (e["home_team"], e["away_team"])
            if k not in tracked:        # only refresh our 16 fixtures
                continue
            h, a = k
            hp, dp, ap = [], [], []
            for bk in e.get("bookmakers", []):
                if bk.get("key") in LAY_BOOKS:
                    continue
                for mk in bk.get("markets", []):
                    if mk["key"] != "h2h":
                        continue
                    o = {x["name"]: x["price"] for x in mk["outcomes"]}
                    if h in o and a in o and "Draw" in o:
                        hp.append(o[h]); dp.append(o["Draw"]); ap.append(o[a])
            if not hp:
                continue
            avg = lambda L: sum(L) / len(L)
            ph, pd, pa = demargin(avg(hp), avg(dp), avg(ap))
            rec = by_key[k]
            new = {**rec, "home": h, "away": a, "date": e["commence_time"][:10],
                   "odds_1x2": [avg(hp), avg(dp), avg(ap)],
                   "fair_1x2": [round(ph, 4), round(pd, 4), round(pa, 4)],
                   "source": f"TheOddsAPI / {len(hp)} books (h2h)"}
            if new != rec:
                by_key[k] = new
                changed = True
    else:
        print("  all fixtures decided — skipping odds fetch", file=sys.stderr)

    market["matches"] = list(by_key.values())
    (HERE / "odds_market.json").write_text(json.dumps(market, indent=1, ensure_ascii=False))
    (HERE / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"odds_market.json: {len(market['matches'])} fixtures · "
          f"results.json: {len(results)} decided · changed={changed}")


if __name__ == "__main__":
    main()
