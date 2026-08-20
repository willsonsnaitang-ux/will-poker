# Will Poker — PRD & Status

## Original problem statement
Build a playable No-Limit Hold'em cash-table MVP for **Will Poker**, a real-money
online poker platform for Canada. v1 scope: auth + lobby + one/several 6-max NLH
cash tables with full NLH rules, WebSocket real-time play, and hand history.

Product requirements:
- React frontend + FastAPI backend + MongoDB
- JWT email/password auth
- Play-money chips only for v1
- Real-time multiplayer WebSocket game-state sync
- Dark casino-inspired design (deep green felt, gold/white accents)

## Architecture
```
/app/backend/
  server.py         REST API (/api/*), WebSocket /api/ws/table/{id}, CORS, shutdown cash-out
  auth.py           JWT auth (bcrypt, access+refresh cookies, ws-token, admin seed, login lockout)
  table_manager.py  TableRuntime per table: clients, asyncio lock, broadcast, turn timer, next-hand scheduler, hand persistence
  poker/game.py     Server-authoritative NLH engine (blinds, streets, betting rules, side pots, showdown)
  poker/deck.py, poker/evaluator.py
  tests/            pytest suite (77 tests) + diagnostic scripts
/app/frontend/src/
  pages/            Landing, Login, Signup, Lobby, Table, Profile, Admin
  components/poker/ Card, Seat, ActionPanel
  context/AuthContext.js, lib/api.js
```

DB collections: `users`, `tables_config`, `hands`, `audit_log`, `login_attempts`.
Table seat/stack state is IN-MEMORY; on graceful shutdown every seated stack is
returned to the player's bankroll.

## Implemented (as of 2026-06 / verified June 2026)
Phase 1–2 — MVP complete and E2E verified:
- Auth: register / login / logout / me / refresh / ws-token, bcrypt hashing,
  admin seeding, brute-force lockout (5 fails → 423 for 15 min, keyed by email)
- Lobby: 4 seeded 6-max cash tables (1/2, 5/10, 10/20, 25/50), search + stake filter
- Buy-in modal with bankroll debit; leave returns stack (reports `forfeited_to_pot`)
- Full NLH engine: blinds (heads-up dealer=SB), preflop BB option, min-raise
  enforcement, all-in + side pots, showdown evaluation, uncontested wins
- Continuous cash game: hands auto-deal 4s after the previous hand ends, dealer
  button rotates, SB/BB derived from the active-seat rotation
- Real-time WS: per-viewer state (hole-card privacy), turn timer (25s auto
  check/fold), chat, reconnect restores seat, sit-out message
- Hand history persisted to `hands` and rendered on Profile
- Admin: stats, user list with search + 25-row paging, manual bankroll adjust, 403 for non-admins
- Dark casino UI: 900x450 felt oval, 6 seats, dealer button, bet chips, winner
  pill with humanised hand names, next-hand countdown

### Bug fixes (June 2026 session)
- P0 re-entrant `asyncio.Lock` deadlock in `TableRuntime._post_action_flow` that
  bricked a table after the first hand (also hung join/leave with 504)
- P0 only-one-hand-per-table (`can_start_hand` never allowed a new hand)
- P0 `sb_seat == bb_seat` from hand 2 onward (blinds derived from stale folded flags)
- P0 big blind never got the preflop option (added per-street `acted` set)
- P0 frontend 0x0 table collapse (fit-content flex child → `w-full`)
- Mid-hand joiners are no longer dealt into the running hand
- Chips no longer vanish on backend restart (shutdown cash-out)
- CORS: explicit origin instead of `*` with credentials (platform edge proxy still
  rewrites the public response to `*` — outside application control)
- UI: username + humanised hand in winner banner, leave button loading state,
  Raise-vs-Bet label on the BB option, final pot shown at showdown

### Testing status
- Backend: `pytest` 77/77 pass (`/app/backend/tests`)
- Two-client WS gameplay verified by script (`tests/diag_verbose.py`): 4
  consecutive hands, alternating blinds, chat, 0.1s leave
- Frontend: testing agent iterations 2, 3, 4 (`/app/test_reports/iteration_*.json`)
  — all P0/P1 items pass as of iteration 4

## Backlog
P1
- Rake calculation (currently hard-coded 0) and rake reporting
- Sit-out / sit-in UI control + auto sit-out on disconnect timeout
- Time-bank on top of the 25s action timer
- Persist seat/stack state so an ungraceful crash cannot lose chips
- Lobby: show "Return to table" instead of the buy-in modal when already seated
- Multi-table view / table filters beyond stakes

P2
- Tournaments: Sit & Go and MTTs with prize pools
- Richer admin dashboard (tables, tournaments, audit-log browser)
- Sound effects, chip/card animations, showdown reveal sequencing
- Real-money rails (KYC, deposits/withdrawals) — explicitly out of scope for v1
