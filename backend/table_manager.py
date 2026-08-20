"""In-memory table manager coordinating games and WebSocket broadcasting."""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from poker.game import PokerGame


ACTION_TIMEOUT_SECONDS = 25
NEXT_HAND_DELAY_SECONDS = 4


class TableRuntime:
    def __init__(self, meta: dict, db):
        self.meta = meta  # id, name, stakes, buy_in_min/max, max_seats
        self.db = db
        self.game = PokerGame(
            table_id=meta["id"],
            small_blind=meta["small_blind"],
            big_blind=meta["big_blind"],
            max_seats=meta["max_seats"],
        )
        self.clients: dict[str, set] = {}  # user_id -> set of WebSockets
        self.lock = asyncio.Lock()
        self.chat: list[dict] = []
        self.turn_deadline: Optional[float] = None
        self._timer_task: Optional[asyncio.Task] = None
        self._next_hand_task: Optional[asyncio.Task] = None
        self.next_hand_at: Optional[float] = None

    def num_seated(self) -> int:
        return len(self.game.seats)

    def snapshot(self, viewer_id: Optional[str] = None) -> dict:
        state = self.game.public_state(viewer_id)
        state["meta"] = self.meta
        state["chat"] = self.chat[-30:]
        state["turn_deadline"] = self.turn_deadline
        state["next_hand_at"] = self.next_hand_at
        state["server_time"] = time.time()
        return state

    async def broadcast(self):
        # per-viewer state (hole cards masking)
        dead = []
        for uid, sockets in self.clients.items():
            state = self.snapshot(uid)
            for ws in list(sockets):
                try:
                    await ws.send_json({"type": "state", "state": state})
                except Exception:
                    dead.append((uid, ws))
        for uid, ws in dead:
            self.clients.get(uid, set()).discard(ws)

    async def add_client(self, user_id: str, ws):
        self.clients.setdefault(user_id, set()).add(ws)

    async def remove_client(self, user_id: str, ws):
        s = self.clients.get(user_id)
        if s:
            s.discard(ws)
            if not s:
                self.clients.pop(user_id, None)

    async def maybe_start_hand(self):
        """Start a hand if possible. Caller must already hold self.lock."""
        if self.game.can_start_hand():
            self.game.start_hand()
            self.next_hand_at = None
            self._start_turn_timer()

    def _start_turn_timer(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self.turn_deadline = time.time() + ACTION_TIMEOUT_SECONDS
        self._timer_task = asyncio.create_task(self._turn_watchdog())

    async def _turn_watchdog(self):
        try:
            await asyncio.sleep(ACTION_TIMEOUT_SECONDS + 0.5)
            async with self.lock:
                if not self.game.hand or self.game.hand.ended:
                    return
                seat = self.game.hand.to_act
                if seat is None:
                    return
                p = self.game.seats.get(seat)
                if not p:
                    return
                # auto: check if possible, else fold
                legal = self.game.legal_actions(seat)
                try:
                    if legal.get("can_check"):
                        self.game.act(p.user_id, "check")
                    else:
                        self.game.act(p.user_id, "fold")
                except Exception:
                    return
                await self._post_action_flow()
        except asyncio.CancelledError:
            return

    async def _post_action_flow(self):
        """Called with self.lock held. Never re-acquires the lock."""
        if self.game.hand and self.game.hand.ended:
            current = asyncio.current_task()
            if self._timer_task and not self._timer_task.done() and self._timer_task is not current:
                self._timer_task.cancel()
            self.turn_deadline = None
            await self._persist_hand()
            self._schedule_next_hand()
            await self.broadcast()
        else:
            self._start_turn_timer()
            await self.broadcast()

    def _schedule_next_hand(self):
        if self._next_hand_task and not self._next_hand_task.done():
            return
        self.next_hand_at = time.time() + NEXT_HAND_DELAY_SECONDS
        self._next_hand_task = asyncio.create_task(self._next_hand_after_delay())

    async def _next_hand_after_delay(self):
        try:
            await asyncio.sleep(NEXT_HAND_DELAY_SECONDS)
            async with self.lock:
                self.next_hand_at = None
                await self.maybe_start_hand()
                await self.broadcast()
        except asyncio.CancelledError:
            self.next_hand_at = None
            return
        except Exception:
            self.next_hand_at = None
            logging.exception("failed to start next hand on table %s", self.meta.get("id"))

    async def _persist_hand(self):
        h = self.game.hand
        if not h:
            return
        # rake: 5% of pot won at showdown-eligible pot (skip if uncontested win)
        rake = 0
        doc = {
            "id": h.hand_id,
            "table_id": self.meta["id"],
            "hand_number": self.game.hand_number,
            "played_at": datetime.now(timezone.utc).isoformat(),
            "board": h.board,
            "winners": h.winners,
            "action_log": h.action_log,
            "players": [
                {
                    "user_id": p.user_id, "username": p.username,
                    "seat": p.seat, "hole_cards": p.hole_cards,
                    "committed": p.total_committed,
                }
                for p in self.game.seats.values() if p.total_committed > 0
            ],
            "rake": rake,
        }
        await self.db.hands.insert_one(doc)

    async def cash_out_all(self):
        """Return every seated player's stack to their bankroll (used on shutdown)."""
        for seat in list(self.game.seats.keys()):
            p = self.game.seats.pop(seat)
            if p.stack > 0:
                await self.db.users.update_one(
                    {"id": p.user_id}, {"$inc": {"bankroll": p.stack}}
                )


class TableManager:
    def __init__(self, db):
        self.db = db
        self.tables: dict[str, TableRuntime] = {}

    async def bootstrap_default_tables(self):
        # Create a few default cash tables if none exist
        cursor = self.db.tables_config.find({})
        existing = await cursor.to_list(100)
        if not existing:
            defaults = [
                {"name": "Maple Leaf", "small_blind": 5, "big_blind": 10, "max_seats": 6,
                 "buy_in_min": 200, "buy_in_max": 1000},
                {"name": "Rideau Rapids", "small_blind": 10, "big_blind": 20, "max_seats": 6,
                 "buy_in_min": 400, "buy_in_max": 2000},
                {"name": "Niagara Nightly", "small_blind": 25, "big_blind": 50, "max_seats": 6,
                 "buy_in_min": 1000, "buy_in_max": 5000},
                {"name": "Yukon Grinders", "small_blind": 1, "big_blind": 2, "max_seats": 6,
                 "buy_in_min": 40, "buy_in_max": 200},
            ]
            for d in defaults:
                d["id"] = str(uuid.uuid4())
                d["stakes"] = f"{d['small_blind']}/{d['big_blind']}"
                await self.db.tables_config.insert_one(d)
                existing.append(d)
        for meta in existing:
            meta.pop("_id", None)
            if meta["id"] not in self.tables:
                self.tables[meta["id"]] = TableRuntime(meta, self.db)

    def list_tables(self) -> list[dict]:
        out = []
        for t in self.tables.values():
            out.append({
                **t.meta,
                "seated": t.num_seated(),
                "in_hand": t.game.hand is not None and not (t.game.hand.ended if t.game.hand else True),
            })
        return out

    async def cash_out_everyone(self):
        for t in self.tables.values():
            await t.cash_out_all()

    def get(self, table_id: str) -> Optional[TableRuntime]:
        return self.tables.get(table_id)
