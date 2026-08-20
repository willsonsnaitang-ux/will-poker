"""Unit-level RCA test: TableRuntime._post_action_flow re-acquires a non-reentrant
asyncio.Lock that its caller already holds -> permanent table deadlock."""
import asyncio
import sys

import pytest

sys.path.insert(0, "/app/backend")

from table_manager import TableRuntime  # noqa: E402


class _StubCollection:
    async def insert_one(self, doc):
        return None

    async def update_one(self, *a, **k):
        return None


class _StubDB:
    def __init__(self):
        self.hands = _StubCollection()
        self.users = _StubCollection()


META = {
    "id": "t-test", "name": "T", "small_blind": 5, "big_blind": 10,
    "max_seats": 6, "buy_in_min": 200, "buy_in_max": 1000, "stakes": "5/10",
}


def test_post_action_flow_does_not_deadlock_table_lock():
    async def scenario():
        t = TableRuntime(dict(META), _StubDB())
        t.game.sit("u1", "p1", 0, 500)
        t.game.sit("u2", "p2", 1, 500)
        async with t.lock:
            await t.maybe_start_hand()
        assert t.game.hand is not None
        # simulate the WebSocket handler: it holds the lock while acting,
        # then calls _post_action_flow (exactly as server.py ws_table does)
        actor_seat = t.game.hand.to_act
        actor = t.game.seats[actor_seat].user_id
        async with t.lock:
            t.game.act(actor, "fold")
            await asyncio.wait_for(t._post_action_flow(), timeout=8)
        # table must be usable afterwards
        await asyncio.wait_for(_acquire(t.lock), timeout=3)

    async def _acquire(lock):
        async with lock:
            return True

    try:
        asyncio.run(scenario())
    except asyncio.TimeoutError:
        pytest.fail(
            "DEADLOCK: _post_action_flow() re-enters `async with self.lock` while the "
            "caller (server.py ws_table / _turn_watchdog) already holds it. asyncio.Lock "
            "is NOT reentrant, so the table lock is held forever -> no further hands, "
            "join/leave hang with 504s."
        )


def test_new_hand_starts_after_hand_ends():
    async def scenario():
        t = TableRuntime(dict(META), _StubDB())
        t.game.sit("u1", "p1", 0, 500)
        t.game.sit("u2", "p2", 1, 500)
        await t.maybe_start_hand()
        first = t.game.hand.hand_id
        actor = t.game.seats[t.game.hand.to_act].user_id
        t.game.act(actor, "fold")
        assert t.game.hand.ended
        await t.maybe_start_hand()
        assert t.game.hand is not None and t.game.hand.hand_id != first, (
            "no second hand dealt: PokerGame.hand is never reset to None after a hand "
            "ends, so can_start_hand() stays False forever"
        )

    asyncio.run(scenario())
