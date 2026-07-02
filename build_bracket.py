#!/usr/bin/env python3
"""Build the data file for the WC2026 knockout-advancement web page.

Input : odds_market.json  (16 Round-of-32 matches, de-margined fair 1X2)
Output: bracket_data.json (teams + calibrated Elo ratings + bracket tree)

Model
-----
A knockout match has no draw: extra-time / penalties resolve it. We map the
market 1X2 into a head-to-head win probability for the listed home side:

    p_win_home = p_home + 0.5 * p_draw      (penalties ~ coin flip)

To show win probabilities for *deeper* rounds (where the opponents are not yet
known) we need one globally-consistent strength number per team. We use Elo:

    p(A beats B) = 1 / (1 + 10**(-(R_A - R_B)/400))

Calibration keeps the model honest where we have data and reasonable where we
don't: each R32 pair's *midpoint* comes from football-prior ratings (so pairs
are comparable across the bracket), while the *rating gap within the pair* is
set to exactly reproduce the market win probability.

Once later-round pairings are realised, refresh.py stores their pre-match
quotes under "knockout" in odds_market.json. Those are applied on top in
kickoff order with the same midpoint-preserving scheme, so every quoted node —
any round — matches the bookmakers to the decimal; only genuinely hypothetical
matchups fall back to the R32-calibrated ratings.
"""

import json
import math
from pathlib import Path

HERE = Path(__file__).parent
ELO_SCALE = 400.0

# Canonical knockout bracket order (top of the bracket to the bottom), keyed by
# home team — odds_market.json is in *chronological* order, which is NOT the
# bracket order. Source: official R32 bracket (verified Jun 2026). The tree
# pairs these sequentially: R16 = (1,2)(3,4)…, then QF, SF, Final. This puts
# France and Spain both in the top half (they can meet no earlier/later than
# the semi-final), Brazil/Argentina in the bottom half, etc.
BRACKET_ORDER = [
    "South Africa", "Netherlands", "Germany", "France",      # top half, QF1 | QF2
    "Belgium", "USA", "Spain", "Portugal",
    "Brazil", "Ivory Coast", "Mexico", "England",            # bottom half, QF3 | QF4
    "Switzerland", "Colombia", "Australia", "Argentina",
]

# Football-prior Elo (approx. World-Football-Elo, mid-2026). Only each R32
# pair's mean matters for cross-bracket scale; the intra-pair gap is overwritten
# by the market during calibration, so these need only rank the pairs sensibly.
PRIOR_ELO = {
    "Argentina": 2090, "France": 2075, "Spain": 2060, "Brazil": 2030,
    "England": 2010, "Portugal": 1995, "Netherlands": 1985, "Germany": 1965,
    "Belgium": 1925, "Croatia": 1900, "Colombia": 1895, "Morocco": 1865,
    "USA": 1850, "Japan": 1835, "Mexico": 1825, "Senegal": 1822,
    "Switzerland": 1818, "Norway": 1810, "Ecuador": 1800, "Austria": 1785,
    "Sweden": 1760, "Ivory Coast": 1755, "Canada": 1748, "Algeria": 1745,
    "Paraguay": 1730, "Australia": 1715, "Bosnia & Herzegovina": 1712,
    "Egypt": 1705, "Ghana": 1700, "DR Congo": 1685, "South Africa": 1680,
    "Cape Verde": 1650,
}

# Short labels for compact bracket cells.
SHORT = {
    "Bosnia & Herzegovina": "Bosnia", "Ivory Coast": "Ivory Coast",
    "DR Congo": "DR Congo", "South Africa": "S. Africa", "Cape Verde": "Cape Verde",
    "Netherlands": "Netherlands", "Switzerland": "Switzerland",
}

# ISO-ish flag emoji per team for a bit of colour.
FLAG = {
    "South Africa": "🇿🇦", "Canada": "🇨🇦", "Brazil": "🇧🇷", "Japan": "🇯🇵",
    "Germany": "🇩🇪", "Paraguay": "🇵🇾", "Netherlands": "🇳🇱", "Morocco": "🇲🇦",
    "Ivory Coast": "🇨🇮", "Norway": "🇳🇴", "France": "🇫🇷", "Sweden": "🇸🇪",
    "Mexico": "🇲🇽", "Ecuador": "🇪🇨", "England": "🏴", "DR Congo": "🇨🇩",
    "Belgium": "🇧🇪", "Senegal": "🇸🇳", "USA": "🇺🇸", "Bosnia & Herzegovina": "🇧🇦",
    "Spain": "🇪🇸", "Austria": "🇦🇹", "Portugal": "🇵🇹", "Croatia": "🇭🇷",
    "Switzerland": "🇨🇭", "Algeria": "🇩🇿", "Australia": "🇦🇺", "Egypt": "🇪🇬",
    "Argentina": "🇦🇷", "Cape Verde": "🇨🇻", "Colombia": "🇨🇴", "Ghana": "🇬🇭",
}


def logit10(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log10(p / (1 - p))


def main():
    market = json.loads((HERE / "odds_market.json").read_text())
    matches = market["matches"]
    assert len(matches) == 16, f"expected 16 R32 matches, got {len(matches)}"

    # Reorder chronological feed into bracket order (top-to-bottom of the tree).
    by_home = {m["home"]: m for m in matches}
    missing = [h for h in BRACKET_ORDER if h not in by_home]
    assert not missing, f"matches missing for bracket slots: {missing}"
    matches = [by_home[h] for h in BRACKET_ORDER]

    # Optional actual results: results.json maps "Home|Away" -> {winner, score}.
    # A decided match advances its winner with certainty (pins the bracket).
    results = {}
    rfile = HERE / "results.json"
    if rfile.exists():
        results = json.loads(rfile.read_text())

    teams = {}
    r32 = []
    for i, m in enumerate(matches):
        home, away = m["home"], m["away"]
        ph, pd, pa = m["fair_1x2"]
        p_home_adv = ph + 0.5 * pd          # knockout win prob for home side

        # Calibrate ratings: keep prior midpoint, set gap to match the market.
        mid = (PRIOR_ELO[home] + PRIOR_ELO[away]) / 2.0
        gap = ELO_SCALE * logit10(p_home_adv)   # R_home - R_away
        r_home = mid + gap / 2.0
        r_away = mid - gap / 2.0

        for name, rating in ((home, r_home), (away, r_away)):
            teams[name] = {
                "name": name,
                "short": SHORT.get(name, name),
                "flag": FLAG.get(name, ""),
                "elo": round(rating, 1),
            }

        r32.append({
            "id": f"R32-{i+1}",
            "home": home,
            "away": away,
            "date": m.get("date"),
            "p_home_adv": round(p_home_adv, 4),  # market-exact, for reference
        })

    # Realised later-round fixtures with market quotes: re-set each pair's
    # rating gap to the market, keeping the pair's midpoint from the ratings
    # calibrated so far. Applied in kickoff order, a team's most recent quote
    # is always the last adjustment it receives, so the model reproduces the
    # market exactly at its next unplayed node (earlier nodes are pinned by
    # results anyway) and deeper hypotheticals inherit the refreshed ratings.
    knockout = market.get("knockout", {})
    for q in sorted(knockout.values(), key=lambda q: q.get("kickoff_utc", "")):
        h, a = q["home"], q["away"]
        if h not in teams or a not in teams:
            continue
        ph, pd, pa = q["fair_1x2"]
        p_home_adv = ph + 0.5 * pd
        mid = (teams[h]["elo"] + teams[a]["elo"]) / 2.0
        gap = ELO_SCALE * logit10(p_home_adv)
        teams[h]["elo"] = round(mid + gap / 2.0, 1)
        teams[a]["elo"] = round(mid - gap / 2.0, 1)

    data = {
        "meta": {
            "title": "World Cup 2026 — Knockout Bracket",
            "source": "TheOddsAPI consensus (de-margined) + calibrated Elo",
            "elo_scale": ELO_SCALE,
            "note": ("Win probabilities reproduce the betting market exactly "
                     "wherever a fixture is quoted (Round of 32, and later "
                     "rounds once their pairings are known); hypothetical "
                     "matchups use calibrated Elo."),
        },
        "teams": teams,
        "r32": r32,
        # Later-round market quotes actually used in calibration, for reference.
        "knockout_market": {k: {"p_home_adv": round(q["fair_1x2"][0] + 0.5 * q["fair_1x2"][1], 4),
                                "date": q.get("date")}
                            for k, q in knockout.items()
                            if q["home"] in teams and q["away"] in teams},
        # Played-match results, any round. Keyed "TeamA|TeamB" (order as played);
        # the client resolves a result wherever those two teams actually meet, so
        # pinning chains from R32 up through the final.
        "results": results,
    }
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    out = HERE / "bracket_data.json"
    out.write_text(payload)
    # Also emit a JS global so index.html works from file:// (no fetch/CORS).
    js = HERE / "bracket_data.js"
    js.write_text("window.BRACKET_DATA = " + payload + ";\n")
    print(f"wrote {out} and {js} — {len(teams)} teams, {len(r32)} R32 matches, "
          f"{len(data['knockout_market'])} later-round market quotes")

    # sanity: top rated teams
    top = sorted(teams.values(), key=lambda t: -t["elo"])[:6]
    print("top Elo:", ", ".join(f"{t['name']} {t['elo']:.0f}" for t in top))


if __name__ == "__main__":
    main()
