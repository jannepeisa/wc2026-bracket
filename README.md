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

- **Quoted fixtures** get their win probabilities straight from the de-margined
  betting market, mapping the 1X2 odds into a knockout win chance as
  `p_home + 0.5·p_draw` (penalties ≈ coin flip). That's all 16 Round-of-32
  games up front, plus each later-round fixture as soon as its pairing is
  realised and bookmakers quote it (stored under `"knockout"` in
  `odds_market.json`). Only **pre-kickoff** quotes are ever stored — once a
  game kicks off the feed switches to in-play prices, which are ignored.
- **Hypothetical matchups** (opponents not yet known) can't use fixed odds, so
  each team gets a **calibrated Elo rating**: the rating gap inside each quoted
  pair is set to reproduce the market exactly, while the pair's midpoint is
  preserved (from football-prior ratings for R32, from the ratings calibrated
  so far for later quotes) so teams stay comparable across the bracket. Any
  matchup is then `1 / (1 + 10^(-(Rₐ−R_b)/400))`. Quotes apply in kickoff
  order, so a team's next unplayed match is always market-exact.
- The bracket pairing follows the **official R32 tree** (see `BRACKET_ORDER` in
  `build_bracket.py`) — note `odds_market.json` is in *chronological* order, not
  bracket order, so the build step reorders it.

## Files

| File | What it is |
|------|------------|
| `index.html` | The whole web page — self-contained CSS + JS, no framework |
| `bracket_data.js` / `.json` | Generated data: teams, calibrated Elo, the 16 R32 matches |
| `build_bracket.py` | Regenerates the data from `odds_market.json` |
| `odds_market.json` | Input: de-margined consensus odds (TheOddsAPI) |
| `results.json` | Played-match results — `{"Home\|Away": {"winner","score"}}` |
| `simulate_bracket.py` | 500k Monte Carlo championship campaign (+ exact check) |
| `refresh.py` | Pulls fresh odds (h2h) + scores, updates the two JSON inputs |
| `update.sh` | refresh → rebuild → commit/push if anything changed (cron entry) |
| `CNAME` | GitHub Pages custom domain |

## Played matches

`results.json` pins completed games (`{"Home|Away": {"winner","score"}}`): the
winner advances with certainty (the bracket cell shows the score + `FT`, the
loser is greyed, and the title odds treat that team as eliminated). Edit it by
hand, or let `refresh.py` fill it from the live scores feed.

**Any round** can be pinned. A result is applied at the node where its two
teams actually meet, and a node is treated as decided only when *both* its
feeders are decided and the realised matchup has a result — so pins chain
R32 → R16 → QF → SF → final, and a modelled (not-yet-played) matchup is never
pinned by accident. A knockout that goes to penalties returns a level score the
scraper can't resolve; add that winner to `results.json` by hand.

## Keeping it fresh

`update.sh` runs `refresh.py` then `build_bracket.py` and pushes only when the
data moved. `refresh.py` makes two cheap Odds-API calls (~2 free-tier credits)
and skips the odds call once the whole tournament is decided. A cron entry every 3 h
(≈16 credits/day) stays comfortably inside the 500-credit monthly free tier:

```cron
0 */3 * * * /path/to/wc2026-bracket/update.sh >> update.log 2>&1
```

It needs a local (gitignored) `.env` with `ODDS_API_KEY=...`.

## Regenerate / run

```bash
python3 build_bracket.py          # rebuild bracket_data.{js,json}
python3 simulate_bracket.py       # print championship odds
python3 -m http.server 8000       # then open http://localhost:8000/
```

It also works opened directly (`file://`) — the data loads as a plain
`<script>`, not via `fetch`.

Hosted on GitHub Pages. 🤖 Built with [Claude Code](https://claude.com/claude-code).
