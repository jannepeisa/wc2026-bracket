#!/usr/bin/env python3
"""Economically refresh odds + results for the WC2026 bracket.

Two cheap Odds-API calls (free-tier credits in brackets):
  - scores  GET /scores                      [1 credit]  -> results.json winners
  - odds    GET /odds  markets=h2h regions=eu [1 credit]  -> odds_market.json 1X2

The 16 R32 fixtures refresh in place. Any OTHER upcoming match between two
bracket teams is, in a single-elimination tournament, a realised later-round
fixture (R16/QF/SF/final) — its quote is stored under "knockout" so
build_bracket.py can calibrate Elo to the market there too. A played fixture
leaves the odds feed but keeps its last pre-kickoff quote and gets pinned in
results.json. Once the whole tournament is decided the odds call is skipped,
so spending tapers to ~1 credit/run and then 0.

Budget math: at ~2 credits/run, every 3 h (8 runs/day) ≈ 16 credits/day, well
within the 500/month free tier across the ~3-week knockout stage.

Usage:  ODDS_API_KEY=... python3 refresh.py
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
SPORT = "soccer_fifa_world_cup"
BASE = f"https://api.the-odds-api.com/v4/sports/{SPORT}"
LAY_BOOKS = {"betfair_ex_eu", "betfair_ex_uk", "matchbook"}
# Datetime (not just date) cutoff: the last group games kicked off ~06-28 03:00Z,
# the first R32 game at 06-28 19:00Z — a noon cutoff cleanly separates them, so no
# group-stage result can ever be mistaken for a knockout one.
KNOCKOUT_START = "2026-06-28T12:00:00Z"


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
    tracked = set(by_key)  # the 16 R32 fixtures — only these get odds refreshed
    teams = {t for pair in tracked for t in pair}  # all 32 bracket teams

    changed = False

    # --- scores -> results.json (any knockout round) ----------------------
    # A completed game on/after the knockout start, between two bracket teams,
    # is a knockout match — record it. The client pins it at the node where the
    # two teams meet, so this naturally covers R16 / QF / SF / final too.
    try:
        # daysFrom=3 so recently-completed games don't age out of the window
        scores = get(f"{BASE}/scores/?apiKey={key}&daysFrom=3")
    except Exception as e:  # noqa: BLE001
        scores = []
        print(f"scores fetch failed: {e}", file=sys.stderr)
    for e in scores:
        h, a = e["home_team"], e["away_team"]
        if not e.get("completed") or e["commence_time"] < KNOCKOUT_START:
            continue
        if h not in teams or a not in teams:
            continue
        sc = {s["name"]: int(s["score"]) for s in (e.get("scores") or [])
              if s.get("score") is not None}
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

    # --- odds -> odds_market.json (skip once the tournament is decided) ----
    # 31 games decide a 32-team knockout; the scores loop also records the
    # third-place playoff, hence 32 as the "everything is over" count.
    knockout = market.setdefault("knockout", {})
    if len(results) < 2 * len(tracked):
        try:
            events = get(f"{BASE}/odds?apiKey={key}&regions=eu&markets=h2h&oddsFormat=decimal")
        except Exception as e:  # noqa: BLE001
            events = []
            print(f"odds fetch failed: {e}", file=sys.stderr)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for e in events:
            h, a = e["home_team"], e["away_team"]
            if h not in teams or a not in teams:   # not a knockout fixture
                continue
            # Once a match kicks off the feed switches to *in-play* prices,
            # which converge on the live scoreline (e.g. 1.01 for a side that
            # is 2-1 up in the 88th). Those must never overwrite the pre-match
            # odds: build_bracket.py calibrates Elo from them, so a live
            # snapshot wildly inflates/deflates a team's tournament rating.
            if e.get("commence_time", "") <= now:
                print(f"  skip in-play/finished: {h} v {a} "
                      f"(kicked off {e.get('commence_time')})", file=sys.stderr)
                continue
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
            quote = {"home": h, "away": a, "date": e["commence_time"][:10],
                     "kickoff_utc": e["commence_time"],
                     "odds_1x2": [avg(hp), avg(dp), avg(ap)],
                     "fair_1x2": [round(ph, 4), round(pd, 4), round(pa, 4)],
                     "source": f"TheOddsAPI / {len(hp)} books (h2h)"}
            if (h, a) in tracked:                  # one of the 16 R32 fixtures
                rec = by_key[(h, a)]
                new = {**rec, **quote}
                if new != rec:
                    by_key[(h, a)] = new
                    changed = True
            else:                                  # realised R16+ fixture
                if knockout.get(f"{h}|{a}") != quote:
                    knockout[f"{h}|{a}"] = quote
                    changed = True
                    print(f"  knockout quote: {h} v {a} "
                          f"fair={quote['fair_1x2']}", file=sys.stderr)
    else:
        print("  tournament decided — skipping odds fetch", file=sys.stderr)

    market["matches"] = list(by_key.values())
    (HERE / "odds_market.json").write_text(json.dumps(market, indent=1, ensure_ascii=False))
    (HERE / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"odds_market.json: {len(market['matches'])} R32 fixtures · "
          f"{len(knockout)} later-round quotes · "
          f"results.json: {len(results)} decided · changed={changed}")


if __name__ == "__main__":
    main()
