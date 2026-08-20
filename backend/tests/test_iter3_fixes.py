"""Iteration 3 fix-verification tests: BB preflop option, multi-hand flow,
dealer rotation, next-hand scheduling (incl. after turn-timer auto action),
mid-hand joiner, shutdown cash-out."""
import asyncio

import pytest

from poker.game import PokerGame
import table_manager as tm_mod
from table_manager import TableRuntime


def make_game(n, sb=1, bb=2, stack=200):
    g = PokerGame("t", sb, bb, max_seats=6)
    for i in range(n):
        g.sit(f"u{i}", f"user{i}", i, stack)
    return g


# ---------- BB preflop option (NLH rule) ----------
class TestBigBlindOption:
    def test_headsup_sb_call_returns_action_to_bb(self):
        g = make_game(2)
        g.start_hand()
        sb, bb = g.hand.sb_seat, g.hand.bb_seat
        assert g.hand.to_act == sb
        g.act(g.seats[sb].user_id, "call")
        assert g.hand.street == "preflop", "street advanced without BB option"
        assert g.hand.to_act == bb, f"action should return to BB, got {g.hand.to_act}"
        # BB checks -> flop
        g.act(g.seats[bb].user_id, "check")
        assert g.hand.street == "flop"
        assert len(g.hand.board) == 3

    def test_headsup_bb_can_raise_its_option(self):
        g = make_game(2)
        g.start_hand()
        sb, bb = g.hand.sb_seat, g.hand.bb_seat
        g.act(g.seats[sb].user_id, "call")
        g.act(g.seats[bb].user_id, "raise", 6)
        assert g.hand.street == "preflop"
        assert g.hand.to_act == sb, "raise must re-open action to SB"
        g.act(g.seats[sb].user_id, "call")
        assert g.hand.street == "flop"

    def test_three_players_bb_acts_last_and_raise_reopens(self):
        g = make_game(3)
        g.start_hand()
        sb, bb = g.hand.sb_seat, g.hand.bb_seat
        utg = g.hand.to_act
        assert utg not in (sb, bb)
        g.act(g.seats[utg].user_id, "call")
        assert g.hand.to_act == sb
        g.act(g.seats[sb].user_id, "call")
        assert g.hand.street == "preflop", "BB must get the option"
        assert g.hand.to_act == bb
        # BB raises -> action re-opens to the other two
        g.act(g.seats[bb].user_id, "raise", 8)
        assert g.hand.street == "preflop"
        assert g.hand.to_act == utg
        g.act(g.seats[utg].user_id, "call")
        assert g.hand.to_act == sb
        g.act(g.seats[sb].user_id, "call")
        assert g.hand.street == "flop"


# ---------- multi-hand + dealer rotation ----------
class TestMultiHand:
    def test_five_consecutive_hands_rotate_dealer_and_conserve_chips(self):
        g = make_game(3, stack=500)
        total_start = sum(p.stack for p in g.seats.values())
        dealers = []
        for _ in range(5):
            assert g.can_start_hand(), "can_start_hand False after previous hand ended"
            g.start_hand()
            dealers.append(g.hand.dealer_seat)
            guard = 0
            while not g.hand.ended:
                guard += 1
                assert guard < 60, "hand did not terminate"
                seat = g.hand.to_act
                legal = g.legal_actions(seat)
                assert legal, f"no legal actions for seat {seat}"
                if legal["can_check"]:
                    g.act(g.seats[seat].user_id, "check")
                else:
                    g.act(g.seats[seat].user_id, "call")
            assert g.hand.winners
            assert all("username" in w for w in g.hand.winners)
        assert dealers == [0, 1, 2, 0, 1], f"dealer did not rotate: {dealers}"
        assert sum(p.stack for p in g.seats.values()) == total_start
        assert g.hand_number == 5


# ---------- runtime: next hand scheduling ----------
class FakeDB:
    class _Coll:
        def __init__(self):
            self.docs = []
            self.updates = []

        async def insert_one(self, doc):
            self.docs.append(doc)

        async def update_one(self, flt, upd):
            self.updates.append((flt, upd))

    def __init__(self):
        self.hands = self._Coll()
        self.users = self._Coll()


META = {"id": "t1", "name": "T", "small_blind": 1, "big_blind": 2, "max_seats": 6,
        "buy_in_min": 40, "buy_in_max": 200, "stakes": "1/2"}


def test_next_hand_scheduled_after_normal_hand_end(monkeypatch):
    asyncio.run(_next_hand_after_normal_hand_end(monkeypatch))


async def _next_hand_after_normal_hand_end(monkeypatch):
    monkeypatch.setattr(tm_mod, "NEXT_HAND_DELAY_SECONDS", 0.2)
    rt = TableRuntime(dict(META), FakeDB())
    rt.game.sit("a", "A", 0, 100)
    rt.game.sit("b", "B", 1, 100)
    async with rt.lock:
        await rt.maybe_start_hand()
    hand1 = rt.game.hand.hand_id
    # fold to end hand
    async with rt.lock:
        rt.game.act(rt.game.seats[rt.game.hand.to_act].user_id, "fold")
        await rt._post_action_flow()
    assert rt.game.hand.ended
    assert rt.next_hand_at is not None, "next_hand_at not exposed for countdown"
    await asyncio.sleep(0.6)
    assert rt.game.hand.hand_id != hand1, "hand #2 never started"
    assert not rt.game.hand.ended
    assert rt.next_hand_at is None
    # lock must be free
    await asyncio.wait_for(rt.lock.acquire(), timeout=1)
    rt.lock.release()


def test_next_hand_scheduled_after_turn_timer_auto_action(monkeypatch):
    """The turn watchdog auto-folds; a new hand must still be scheduled."""
    asyncio.run(_next_hand_after_timer(monkeypatch))


async def _next_hand_after_timer(monkeypatch):
    monkeypatch.setattr(tm_mod, "ACTION_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(tm_mod, "NEXT_HAND_DELAY_SECONDS", 0.2)
    rt = TableRuntime(dict(META), FakeDB())
    rt.game.sit("a", "A", 0, 100)
    rt.game.sit("b", "B", 1, 100)
    async with rt.lock:
        await rt.maybe_start_hand()
    hand1 = rt.game.hand.hand_id
    # let watchdog fire repeatedly until the hand ends by auto fold/check
    await asyncio.sleep(3.0)
    assert rt.game.hand is not None
    assert rt.game.hand.hand_id != hand1, (
        "no new hand after a hand ended via turn-timer auto action "
        f"(still hand {hand1}, ended={rt.game.hand.ended}, next_hand_at={rt.next_hand_at})"
    )
    await asyncio.wait_for(rt.lock.acquire(), timeout=1)
    rt.lock.release()


def test_cash_out_all_returns_stacks_to_bankroll():
    asyncio.run(_cash_out_all())


async def _cash_out_all():
    db = FakeDB()
    rt = TableRuntime(dict(META), db)
    rt.game.sit("a", "A", 0, 100)
    rt.game.sit("b", "B", 1, 55)
    await rt.cash_out_all()
    assert rt.num_seated() == 0
    credited = {f["id"]: u["$inc"]["bankroll"] for f, u in db.users.updates}
    assert credited == {"a": 100, "b": 55}


def test_midhand_joiner_not_dealt_in_but_dealt_next_hand():
    g = make_game(2)
    g.start_hand()
    p = g.sit("c", "C", 2, 100)
    assert p.folded is True
    assert p.hole_cards == []
    # finish hand
    while not g.hand.ended:
        seat = g.hand.to_act
        legal = g.legal_actions(seat)
        g.act(g.seats[seat].user_id, "check" if legal["can_check"] else "call")
    g.start_hand()
    assert g.seats[2].folded is False
    assert len(g.seats[2].hole_cards) == 2
