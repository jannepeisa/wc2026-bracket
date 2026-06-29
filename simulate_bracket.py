#!/usr/bin/env python3
"""Monte Carlo campaign over the WC2026 knockout bracket.

Reads bracket_data.json (already in bracket order, with calibrated Elo) and
plays out the whole single-elimination tree many times. Reports, per team, the
probability of reaching each round and of winning the tournament.

Win model is identical to the web page:
    p(A beats B) = 1 / (1 + 10**(-(elo_A - elo_B)/400))
R32 matches reproduce the betting market; deeper rounds use calibrated Elo.

A closed-form (exact) calculation is run alongside the simulation as a check —
for an independent-match bracket the round-reach probabilities can be computed
exactly by propagating per-node "winner distributions" up the tree, so the MC
estimates should land within sampling error of them.

Usage:  python3 simulate_bracket.py [--sims 500000] [--seed 1]
"""

import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
ROUND_REACHED = ["Round of 16", "Quarter-final", "Semi-final", "Final", "Champion"]


def load():
    d = json.loads((HERE / "bracket_data.json").read_text())
    elo = {name: t["elo"] for name, t in d["teams"].items()}
    # r32 is already in bracket order; pair sequentially up the tree.
    leaves = [(m["home"], m["away"]) for m in d["r32"]]
    scale = d["meta"]["elo_scale"]
    results = d.get("results", {})
    return elo, leaves, scale, results


def make_pwin(elo, scale, results=None):
    """P(a beats b), forcing a pinned result wherever a and b actually meet."""
    results = results or {}

    def result_for(a, b):
        return results.get(f"{a}|{b}") or results.get(f"{b}|{a}")

    def p(a, b):
        r = result_for(a, b)
        if r and r.get("winner") in (a, b):
            return 1.0 if r["winner"] == a else 0.0
        return 1.0 / (1.0 + 10 ** (-(elo[a] - elo[b]) / scale))
    return p


# ---- exact propagation ----------------------------------------------------
def exact(leaves, pwin):
    """Return reach[team] = [P(R16), P(QF), P(SF), P(Final), P(Champion)].

    Each bracket node carries a dict team->P(team is the winner of this node).
    A team 'reaches round k+1' exactly when it wins its round-k node, so the
    winner-distribution at each level *is* the reach distribution for the next.
    """
    reach = {t: [0.0] * 5 for pair in leaves for t in pair}

    # level 0: R32 matches -> winners reach R16
    nodes = []
    for a, b in leaves:
        pa = pwin(a, b)
        dist = {a: pa, b: 1 - pa}
        for t, pr in dist.items():
            reach[t][0] += pr
        nodes.append(dist)

    level = 1
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            left, right = nodes[i], nodes[i + 1]
            dist = {}
            for t, pt in left.items():
                pw = sum(po * pwin(t, o) for o, po in right.items())
                dist[t] = pt * pw
            for t, pt in right.items():
                pw = sum(po * pwin(t, o) for o, po in left.items())
                dist[t] = pt * pw
            for t, pr in dist.items():
                reach[t][level] += pr
            nxt.append(dist)
        nodes = nxt
        level += 1
    return reach


# ---- monte carlo ----------------------------------------------------------
def simulate(leaves, pwin, sims, seed):
    rng = random.Random(seed)
    counts = {t: [0] * 5 for pair in leaves for t in pair}
    for _ in range(sims):
        round_teams = leaves
        level = 0
        while True:
            winners = []
            for a, b in round_teams:
                w = a if rng.random() < pwin(a, b) else b
                counts[w][level] += 1
                winners.append(w)
            level += 1
            if len(winners) == 1:
                break
            round_teams = [(winners[i], winners[i + 1])
                           for i in range(0, len(winners), 2)]
    return {t: [c / sims for c in row] for t, row in counts.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=500_000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    elo, leaves, scale, results = load()
    pwin = make_pwin(elo, scale, results)

    ex = exact(leaves, pwin)
    mc = simulate(leaves, pwin, args.sims, args.seed)

    order = sorted(ex, key=lambda t: -ex[t][4])
    max_err = max(abs(ex[t][4] - mc[t][4]) for t in ex)

    print(f"Monte Carlo: {args.sims:,} simulated tournaments (seed {args.seed})")
    print(f"max |MC − exact| champion error: {max_err*100:.3f} pp\n")

    hdr = f"{'Team':<22}{'R16':>7}{'QF':>7}{'SF':>7}{'Final':>8}{'CHAMP':>8}{'fair odds':>11}"
    print(hdr)
    print("-" * len(hdr))
    for t in order:
        r = mc[t]
        champ = r[4]
        odds = f"{1/champ:,.0f}-1" if champ > 0 else "—"
        print(f"{t:<22}{r[0]*100:>6.1f}%{r[1]*100:>6.1f}%{r[2]*100:>6.1f}%"
              f"{r[3]*100:>7.1f}%{champ*100:>7.1f}%{odds:>11}")

    # write a machine-readable snapshot too
    out = {
        "meta": {"sims": args.sims, "seed": args.seed, "model": "calibrated Elo",
                 "rounds": ROUND_REACHED},
        "teams": {t: {"reach": {ROUND_REACHED[i]: round(mc[t][i], 5)
                                for i in range(5)},
                      "champion_pct": round(mc[t][4] * 100, 2),
                      "fair_decimal_odds": round(1 / mc[t][4], 2) if mc[t][4] else None}
                  for t in order},
    }
    (HERE / "championship_odds.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"\nwrote championship_odds.json")


if __name__ == "__main__":
    main()
