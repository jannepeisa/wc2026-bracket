# 🏆 World Cup 2026 — Knockout Bracket Predictor

An interactive single-elimination bracket showing each team's chance of
advancing through the 2026 World Cup knockout rounds.

**Live:** https://wc2026-bracket.peisa.fi

- Opens to the **most-likely** bracket — every match auto-advances its
  favourite, all the way to a predicted champion.
- **Click any team** to send them through instead; the whole downstream
  bracket recomputes and a 📌 marks your manual picks. Impossible picks
  (a team eliminated upstream) are pruned automatically.
- Each match shows the **win probability** as a bar width + percentage.

## How the numbers are made

- **Round of 32** win probabilities come straight from the de-margined betting
  market, mapping the 1X2 odds into a knockout win chance as
  `p_home + 0.5·p_draw` (penalties ≈ coin flip).
- **Later rounds** can't use fixed odds because the opponents depend on earlier
  results, so each team gets a **calibrated Elo rating**: the rating gap inside
  each R32 pair is set to reproduce the market exactly, while the pair's
  midpoint comes from football-prior ratings so teams stay comparable across
  the bracket. Any matchup is then `1 / (1 + 10^(-(Rₐ−R_b)/400))`.
- The bracket pairing follows the **official R32 tree** (see `BRACKET_ORDER` in
  `build_bracket.py`) — note `odds_market.json` is in *chronological* order, not
  bracket order, so the build step reorders it.

## Files

| File | What it is |
|------|------------|
| `index.html` | The whole web page — self-contained CSS + JS, no framework |
| `bracket_data.js` / `.json` | Generated data: teams, calibrated Elo, the 16 R32 matches |
| `build_bracket.py` | Regenerates the data from `odds_market.json` |
| `odds_market.json` | Input: de-margined consensus odds (TheOddsAPI, 23 books) |
| `CNAME` | GitHub Pages custom domain |

## Regenerate / run

```bash
python3 build_bracket.py          # rebuild bracket_data.{js,json}
python3 -m http.server 8000       # then open http://localhost:8000/
```

It also works opened directly (`file://`) — the data loads as a plain
`<script>`, not via `fetch`.

Hosted on GitHub Pages. 🤖 Built with [Claude Code](https://claude.com/claude-code).
