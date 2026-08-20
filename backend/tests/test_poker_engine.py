"""Poker engine unit tests: deck, evaluator, betting flow, side pots, hand reset."""
import sys

import pytest

sys.path.insert(0, "/app/backend")

from poker.deck import Deck, full_deck  # noqa: E402
from poker.evaluator import best_hand, category_name, _rank_five  # noqa: E402
from poker.game import PokerGame  # noqa: E402


class TestDeck:
    def test_52_unique_cards(self):
        d = Deck()
        assert len(d.cards) == 52
        assert len(set(d.cards)) == 52
        assert set(d.cards) == set(full_deck())

    def test_draw_removes_cards(self):
        d = Deck()
        drawn = d.draw(5)
        assert len(drawn) == 5
        assert len(d.cards) == 47
        assert not set(drawn) & set(d.cards)

    def test_shuffle_randomises(self):
        a = Deck().cards
        b = Deck().cards
        assert a != b


class TestEvaluator:
    def test_category_ordering(self):
        royal = _rank_five(["As", "Ks", "Qs", "Js", "Ts"])
        sf = _rank_five(["9h", "8h", "7h", "6h", "5h"])
        quads = _rank_five(["9c", "9d", "9h", "9s", "2c"])
        boat = _rank_five(["8c", "8d", "8h", "3s", "3c"])
        flush = _rank_five(["Ad", "Jd", "9d", "5d", "2d"])
        straight = _rank_five(["9c", "8d", "7h", "6s", "5c"])
        trips = _rank_five(["7c", "7d", "7h", "Ks", "2c"])
        two_pair = _rank_five(["Kc", "Kd", "4h", "4s", "9c"])
        pair = _rank_five(["Ac", "Ad", "8h", "5s", "2c"])
        high = _rank_five(["Ac", "Qd", "9h", "6s", "3c"])
        order = [royal, sf, quads, boat, flush, straight, trips, two_pair, pair, high]
        for hi, lo in zip(order, order[1:]):
            assert hi > lo, f"{hi} should beat {lo}"
        assert category_name(royal) == "STRAIGHT_FLUSH"
        assert category_name(quads) == "QUADS"
        assert category_name(two_pair) == "TWO_PAIR"

    def test_wheel_straight(self):
        r = _rank_five(["As", "2c", "3d", "4h", "5s"])
        assert r[0] == 4  # STRAIGHT
        assert r[1] == 5  # five-high

    def test_wheel_loses_to_six_high_straight(self):
        wheel = _rank_five(["As", "2c", "3d", "4h", "5s"])
        six = _rank_five(["6s", "2c", "3d", "4h", "5s"])
        assert six > wheel

    def test_best_hand_from_seven(self):
        rank, five = best_hand(["As", "Ks", "Qs", "Js", "Ts", "2c", "3d"])
        assert category_name(rank) == "STRAIGHT_FLUSH"
        assert len(five) == 5
        assert set(five) == {"As", "Ks", "Qs", "Js", "Ts"}

    def test_flush_kicker_comparison(self):
        a = _rank_five(["Ad", "Kd", "9d", "5d", "2d"])
        b = _rank_five(["Ad", "Qd", "9d", "5d", "2d"])
        assert a > b

    def test_two_pair_kicker(self):
        a = _rank_five(["Kc", "Kd", "4h", "4s", "Ac"])
        b = _rank_five(["Kc", "Kd", "4h", "4s", "9c"])
        assert a > b

    def test_royal_beats_quads_from_seven(self):
        royal, _ = best_hand(["As", "Ks", "Qs", "Js", "Ts", "Ah", "Ad"])
        quads, _ = best_hand(["Ac", "Ah", "Ad", "As", "Ts", "3c", "4d"])
        assert royal > quads


def _game(stacks, sb=5, bb=10):
    g = PokerGame("t1", sb, bb, 6)
    for i, st in enumerate(stacks):
        g.sit(f"u{i}", f"user{i}", i, st)
    return g


class TestBettingFlow:
    def test_blinds_and_deal(self):
        g = _game([1000, 1000, 1000])
        g.start_hand()
        h = g.hand
        assert h.pot == 15
        assert g.seats[h.sb_seat].bet == 5
        assert g.seats[h.bb_seat].bet == 10
        for p in g.seats.values():
            assert len(p.hole_cards) == 2
        all_cards = [c for p in g.seats.values() for c in p.hole_cards]
        assert len(set(all_cards)) == len(all_cards), "duplicate hole cards dealt"
        assert h.to_act is not None
        assert h.current_bet == 10

    def test_uncontested_fold_awards_pot(self):
        g = _game([1000, 1000])
        g.start_hand()
        h = g.hand
        # heads-up: dealer/SB acts first
        actor = g.seats[h.to_act]
        g.act(actor.user_id, "fold")
        assert g.hand.ended is True
        assert len(g.hand.winners) == 1
        assert g.hand.winners[0]["reason"] == "uncontested"
        assert g.hand.winners[0]["amount"] == 15

    def test_big_blind_gets_option_to_raise_preflop(self):
        """NLH rule: after SB completes, BB must get the option to act."""
        g = _game([1000, 1000, 1000])
        g.start_hand()
        h = g.hand
        order = []
        guard = 0
        while g.hand and not g.hand.ended and g.hand.street == "preflop" and guard < 10:
            guard += 1
            seat = g.hand.to_act
            order.append(seat)
            g.act(g.seats[seat].user_id, "call" if g.legal_actions(seat)["to_call"] > 0 else "check")
        assert h.bb_seat in order, (
            f"BB (seat {h.bb_seat}) never got to act preflop; acting order was {order}")

    def test_full_hand_to_showdown(self):
        g = _game([1000, 1000])
        g.start_hand()
        guard = 0
        while g.hand and not g.hand.ended and guard < 40:
            guard += 1
            seat = g.hand.to_act
            if seat is None:
                break
            legal = g.legal_actions(seat)
            action = "check" if legal.get("can_check") else "call"
            g.act(g.seats[seat].user_id, action)
        assert g.hand.ended is True, f"hand did not end; street={g.hand.street}"
        assert len(g.hand.board) == 5, f"board has {len(g.hand.board)} cards"
        assert len(g.hand.winners) >= 1
        total = sum(p.stack for p in g.seats.values())
        assert total == 2000, f"chip conservation broken: {total}"

    def test_min_raise_enforced(self):
        g = _game([1000, 1000, 1000])
        g.start_hand()
        seat = g.hand.to_act
        with pytest.raises(RuntimeError):
            g.act(g.seats[seat].user_id, "raise", 15)  # below min raise (needs 20)

    def test_act_out_of_turn_rejected(self):
        g = _game([1000, 1000, 1000])
        g.start_hand()
        seat = g.hand.to_act
        other = next(s for s in g.seats if s != seat)
        with pytest.raises(RuntimeError):
            g.act(g.seats[other].user_id, "fold")

    def test_new_hand_can_start_after_previous_ends(self):
        """After a hand ends the engine must be ready to deal the next one."""
        g = _game([1000, 1000])
        g.start_hand()
        g.act(g.seats[g.hand.to_act].user_id, "fold")
        assert g.hand.ended is True
        assert g.can_start_hand() is True, (
            "can_start_hand() is False after hand ended - hand state never reset, "
            "so no new hand will ever be dealt")


class TestSidePots:
    def test_three_way_two_all_ins_side_pot_distribution(self):
        g = _game([100, 300, 1000], sb=5, bb=10)
        g.start_hand()
        # force known cards: seat0 nut hand, seat1 second, seat2 worst
        g.hand.board = []
        g.seats[0].hole_cards = ["As", "Ks"]
        g.seats[1].hole_cards = ["Ah", "Kh"]
        g.seats[2].hole_cards = ["2c", "3d"]
        guard = 0
        while g.hand and not g.hand.ended and guard < 40:
            guard += 1
            seat = g.hand.to_act
            if seat is None:
                break
            legal = g.legal_actions(seat)
            if legal.get("can_bet_or_raise"):
                g.act(g.seats[seat].user_id, "raise", legal["max_raise_total"])
            elif legal.get("can_call"):
                g.act(g.seats[seat].user_id, "call")
            else:
                g.act(g.seats[seat].user_id, "check")
        assert g.hand.ended is True
        total = sum(p.stack for p in g.seats.values())
        assert total == 1400, f"chip conservation broken in side pots: {total}"
        # nobody can win more than they were eligible for
        assert g.seats[0].stack <= 300, (
            f"short stack (100) won {g.seats[0].stack} - exceeds main-pot cap")
        assert sum(w["amount"] for w in g.hand.winners) > 0
