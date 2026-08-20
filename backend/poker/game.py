"""No-Limit Texas Hold'em game engine (server-authoritative).

Handles: blinds, betting rounds (preflop/flop/turn/river), min-raise rules,
all-in + side pots, hand comparison, and pot distribution. All state is
plain Python; persistence + WebSocket broadcasting is handled by callers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from .deck import Deck
from .evaluator import best_hand, category_name


STREETS = ["preflop", "flop", "turn", "river", "showdown"]


@dataclass
class Player:
    user_id: str
    username: str
    seat: int
    stack: int
    hole_cards: list[str] = field(default_factory=list)
    bet: int = 0  # current-street bet
    total_committed: int = 0  # committed this hand
    folded: bool = False
    all_in: bool = False
    sitting_out: bool = False
    connected: bool = True
    last_action: Optional[str] = None


@dataclass
class HandState:
    hand_id: str
    dealer_seat: int
    sb_seat: int
    bb_seat: int
    small_blind: int
    big_blind: int
    board: list[str] = field(default_factory=list)
    pot: int = 0
    current_bet: int = 0
    min_raise: int = 0
    to_act: Optional[int] = None  # seat index
    street: str = "preflop"
    last_aggressor: Optional[int] = None
    acted: set = field(default_factory=set)  # seats that acted on current street
    ended: bool = False
    winners: list[dict] = field(default_factory=list)
    action_log: list[dict] = field(default_factory=list)


class PokerGame:
    def __init__(
        self,
        table_id: str,
        small_blind: int,
        big_blind: int,
        max_seats: int = 6,
    ):
        self.table_id = table_id
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.max_seats = max_seats
        self.seats: dict[int, Player] = {}
        self.dealer_seat: Optional[int] = None
        self.hand: Optional[HandState] = None
        self.hand_number = 0

    # ---------- seat management ----------
    def sit(self, user_id: str, username: str, seat: int, buy_in: int) -> Player:
        if seat < 0 or seat >= self.max_seats:
            raise ValueError("invalid seat")
        if seat in self.seats:
            raise ValueError("seat taken")
        if any(p.user_id == user_id for p in self.seats.values()):
            raise ValueError("already seated at this table")
        p = Player(user_id=user_id, username=username, seat=seat, stack=buy_in)
        # joining mid-hand: wait for the next hand
        if self.hand is not None and not self.hand.ended:
            p.folded = True
        self.seats[seat] = p
        return p

    def stand(self, user_id: str) -> int:
        seat = self._seat_of(user_id)
        if seat is None:
            return 0
        p = self.seats.pop(seat)
        # if hand in progress, forfeit current-hand chips (already in pot)
        return p.stack

    def _seat_of(self, user_id: str) -> Optional[int]:
        for s, p in self.seats.items():
            if p.user_id == user_id:
                return s
        return None

    def active_seats(self) -> list[int]:
        return sorted(
            s for s, p in self.seats.items()
            if not p.sitting_out and p.stack > 0
        )

    # ---------- hand flow ----------
    def can_start_hand(self) -> bool:
        if self.hand is not None and not self.hand.ended:
            return False
        return len(self.active_seats()) >= 2

    def start_hand(self):
        active = self.active_seats()
        if len(active) < 2:
            raise RuntimeError("need 2+ active players")

        # Advance dealer button
        if self.dealer_seat is None or self.dealer_seat not in active:
            self.dealer_seat = active[0]
        else:
            idx = active.index(self.dealer_seat)
            self.dealer_seat = active[(idx + 1) % len(active)]

        # Blinds are derived from the active-seat rotation (never from stale
        # folded flags left over by the previous hand).
        d_idx = active.index(self.dealer_seat)
        if len(active) == 2:
            # Heads-up: dealer posts SB
            sb_seat = self.dealer_seat
            bb_seat = active[(d_idx + 1) % len(active)]
        else:
            sb_seat = active[(d_idx + 1) % len(active)]
            bb_seat = active[(d_idx + 2) % len(active)]

        self.hand_number += 1
        self.hand = HandState(
            hand_id=str(uuid.uuid4()),
            dealer_seat=self.dealer_seat,
            sb_seat=sb_seat,
            bb_seat=bb_seat,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
        )

        # Reset players
        for p in self.seats.values():
            p.hole_cards = []
            p.bet = 0
            p.total_committed = 0
            p.folded = p.sitting_out or p.stack == 0
            p.all_in = False
            p.last_action = None

        # Post blinds
        self._post_blind(sb_seat, self.small_blind)
        self._post_blind(bb_seat, self.big_blind)
        self.hand.current_bet = self.big_blind
        self.hand.min_raise = self.big_blind
        self.hand.last_aggressor = bb_seat

        # Deal hole cards
        deck = Deck()
        self._deck = deck
        order = self._acting_order_from(self._next_active(bb_seat))
        for _ in range(2):
            for s in order:
                self.seats[s].hole_cards.extend(deck.draw(1))

        # First to act preflop is left of BB (or SB in heads-up)
        if len(active) == 2:
            self.hand.to_act = sb_seat
        else:
            self.hand.to_act = self._next_active(bb_seat)

    def _post_blind(self, seat: int, amount: int):
        p = self.seats[seat]
        post = min(amount, p.stack)
        p.stack -= post
        p.bet = post
        p.total_committed += post
        self.hand.pot += post
        if p.stack == 0:
            p.all_in = True
        self.hand.action_log.append(
            {"seat": seat, "action": "blind", "amount": post}
        )

    def _next_active(self, seat: int) -> int:
        seats_in_hand = sorted(
            s for s, p in self.seats.items()
            if not p.folded and not p.sitting_out
        )
        if not seats_in_hand:
            return seat
        # rotate
        greater = [s for s in seats_in_hand if s > seat]
        return greater[0] if greater else seats_in_hand[0]

    def _acting_order_from(self, start_seat: int) -> list[int]:
        seats_in_hand = sorted(
            s for s, p in self.seats.items()
            if not p.folded and not p.sitting_out and not p.all_in
        )
        if not seats_in_hand:
            return []
        if start_seat in seats_in_hand:
            i = seats_in_hand.index(start_seat)
        else:
            # first seat >= start
            after = [s for s in seats_in_hand if s >= start_seat]
            i = seats_in_hand.index(after[0]) if after else 0
        return seats_in_hand[i:] + seats_in_hand[:i]

    # ---------- actions ----------
    def legal_actions(self, seat: int) -> dict:
        if self.hand is None or self.hand.ended:
            return {}
        if self.hand.to_act != seat:
            return {}
        p = self.seats.get(seat)
        if p is None or p.folded or p.all_in:
            return {}
        to_call = self.hand.current_bet - p.bet
        can_check = to_call == 0
        can_call = to_call > 0
        # min bet/raise
        min_raise_total = self.hand.current_bet + self.hand.min_raise
        max_raise_total = p.stack + p.bet  # all-in
        can_bet_or_raise = p.stack > to_call
        return {
            "to_call": to_call,
            "can_check": can_check,
            "can_call": can_call,
            "can_bet_or_raise": can_bet_or_raise,
            "min_raise_total": min(min_raise_total, max_raise_total),
            "max_raise_total": max_raise_total,
            "stack": p.stack,
            "pot": self.hand.pot,
        }

    def act(self, user_id: str, action: str, amount: int = 0):
        if self.hand is None or self.hand.ended:
            raise RuntimeError("no active hand")
        seat = self._seat_of(user_id)
        if seat is None or seat != self.hand.to_act:
            raise RuntimeError("not your turn")
        p = self.seats[seat]
        to_call = self.hand.current_bet - p.bet

        if action == "fold":
            p.folded = True
            p.last_action = "fold"
            self.hand.action_log.append({"seat": seat, "action": "fold"})
        elif action == "check":
            if to_call != 0:
                raise RuntimeError("cannot check")
            p.last_action = "check"
            self.hand.action_log.append({"seat": seat, "action": "check"})
        elif action == "call":
            if to_call <= 0:
                raise RuntimeError("nothing to call")
            pay = min(to_call, p.stack)
            p.stack -= pay
            p.bet += pay
            p.total_committed += pay
            self.hand.pot += pay
            if p.stack == 0:
                p.all_in = True
            p.last_action = "call"
            self.hand.action_log.append(
                {"seat": seat, "action": "call", "amount": pay}
            )
        elif action in ("bet", "raise"):
            # amount is target TOTAL bet on this street
            target = int(amount)
            if target <= self.hand.current_bet:
                raise RuntimeError("raise must exceed current bet")
            need = target - p.bet
            if need > p.stack:
                # treat as all-in
                target = p.bet + p.stack
                need = p.stack
            raise_size = target - self.hand.current_bet
            is_all_in = need == p.stack
            if raise_size < self.hand.min_raise and not is_all_in:
                raise RuntimeError("raise below minimum")
            p.stack -= need
            p.bet = target
            p.total_committed += need
            self.hand.pot += need
            if raise_size >= self.hand.min_raise:
                self.hand.min_raise = raise_size
            self.hand.current_bet = target
            self.hand.last_aggressor = seat
            if p.stack == 0:
                p.all_in = True
            p.last_action = action
            self.hand.action_log.append(
                {"seat": seat, "action": action, "amount": target}
            )
        else:
            raise RuntimeError(f"unknown action {action}")

        if action in ("bet", "raise"):
            # aggression re-opens the action for everyone else
            self.hand.acted = {seat}
        else:
            self.hand.acted.add(seat)

        self._advance_action()

    def _advance_action(self):
        # if only one player left, award pot
        remaining = [s for s, p in self.seats.items() if not p.folded and not p.sitting_out]
        if len(remaining) == 1:
            self._end_hand_no_showdown(remaining[0])
            return
        next_seat = self._next_to_act(self.hand.to_act)
        if next_seat is None:
            # every actionable player has acted and matched the current bet
            self._advance_street()
            return
        self.hand.to_act = next_seat

    def _actionable_cycle(self, from_seat: int) -> list[int]:
        """Actionable seats in order after `from_seat` (from_seat comes last)."""
        seats_in_hand = sorted(
            s for s, p in self.seats.items()
            if not p.folded and not p.sitting_out and not p.all_in
        )
        after = [s for s in seats_in_hand if s > from_seat]
        before = [s for s in seats_in_hand if s <= from_seat]
        return after + before

    def _next_to_act(self, from_seat: int) -> Optional[int]:
        for s in self._actionable_cycle(from_seat):
            p = self.seats[s]
            if s not in self.hand.acted or p.bet != self.hand.current_bet:
                return s
        return None

    def _advance_street(self):
        # reset street bets
        for p in self.seats.values():
            p.bet = 0
            if not p.folded and not p.all_in:
                p.last_action = None
        self.hand.current_bet = 0
        self.hand.min_raise = self.big_blind
        self.hand.acted = set()
        self.hand.last_aggressor = None
        idx = STREETS.index(self.hand.street)
        next_street = STREETS[idx + 1] if idx + 1 < len(STREETS) else "showdown"
        self.hand.street = next_street

        if next_street == "flop":
            self._deck.draw(1)  # burn
            self.hand.board.extend(self._deck.draw(3))
        elif next_street == "turn":
            self._deck.draw(1)
            self.hand.board.extend(self._deck.draw(1))
        elif next_street == "river":
            self._deck.draw(1)
            self.hand.board.extend(self._deck.draw(1))

        if next_street == "showdown":
            self._showdown()
            return

        # if everyone remaining is all-in, deal remaining streets then showdown
        actionable = [s for s, p in self.seats.items() if not p.folded and not p.all_in]
        if len(actionable) < 2:
            # deal to river then showdown
            while self.hand.street != "river":
                self._advance_street()
                if self.hand.ended:
                    return
            self._showdown()
            return

        # first to act post-flop: left of dealer among actionable
        self.hand.to_act = self._next_to_act(self.hand.dealer_seat)

    def _end_hand_no_showdown(self, winner_seat: int):
        p = self.seats[winner_seat]
        p.stack += self.hand.pot
        self.hand.winners = [{
            "seat": winner_seat, "user_id": p.user_id, "username": p.username,
            "amount": self.hand.pot, "reason": "uncontested",
        }]
        self.hand.pot = 0
        self.hand.ended = True
        self.hand.to_act = None

    def _showdown(self):
        # Compute side pots based on total_committed levels
        contenders = [p for p in self.seats.values() if not p.folded and not p.sitting_out]
        # include folded contribs (dead money) — use all seats that put chips in
        all_players = [p for p in self.seats.values() if p.total_committed > 0]
        levels = sorted({p.total_committed for p in contenders})
        prev = 0
        pots = []  # list of (amount, eligible_user_ids)
        for lvl in levels:
            amt = 0
            for p in all_players:
                contrib = max(0, min(p.total_committed, lvl) - prev)
                amt += contrib
            eligible = [p.user_id for p in contenders if p.total_committed >= lvl]
            if amt > 0:
                pots.append((amt, eligible))
            prev = lvl

        # rank each contender
        rankings = {}
        for p in contenders:
            r, five = best_hand(p.hole_cards + self.hand.board)
            rankings[p.user_id] = (r, five)

        winners_list = []
        for pot_amount, eligible in pots:
            best_r = max(rankings[uid][0] for uid in eligible)
            pot_winners = [uid for uid in eligible if rankings[uid][0] == best_r]
            share = pot_amount // len(pot_winners)
            remainder = pot_amount - share * len(pot_winners)
            for i, uid in enumerate(pot_winners):
                extra = 1 if i < remainder else 0
                seat = self._seat_of(uid)
                self.seats[seat].stack += share + extra
                winners_list.append({
                    "seat": seat, "user_id": uid,
                    "username": self.seats[seat].username,
                    "amount": share + extra,
                    "hand": category_name(rankings[uid][0]),
                    "best_five": rankings[uid][1],
                })

        self.hand.winners = winners_list
        self.hand.pot = 0
        self.hand.ended = True
        self.hand.to_act = None

    # ---------- serialization ----------
    def public_state(self, viewer_user_id: Optional[str] = None) -> dict:
        players_out = []
        for seat, p in sorted(self.seats.items()):
            reveal = False
            if self.hand and self.hand.ended and not p.folded:
                reveal = True
            if viewer_user_id and p.user_id == viewer_user_id:
                reveal = True
            players_out.append({
                "seat": seat,
                "user_id": p.user_id,
                "username": p.username,
                "stack": p.stack,
                "bet": p.bet,
                "folded": p.folded,
                "all_in": p.all_in,
                "sitting_out": p.sitting_out,
                "connected": p.connected,
                "last_action": p.last_action,
                "hole_cards": p.hole_cards if reveal else (["?", "?"] if p.hole_cards else []),
            })

        hand_out = None
        if self.hand:
            hand_out = {
                "hand_id": self.hand.hand_id,
                "hand_number": self.hand_number,
                "dealer_seat": self.hand.dealer_seat,
                "sb_seat": self.hand.sb_seat,
                "bb_seat": self.hand.bb_seat,
                "board": self.hand.board,
                "pot": self.hand.pot,
                "current_bet": self.hand.current_bet,
                "min_raise": self.hand.min_raise,
                "to_act": self.hand.to_act,
                "street": self.hand.street,
                "ended": self.hand.ended,
                "winners": self.hand.winners,
                "action_log": self.hand.action_log[-20:],
            }

        legal = {}
        if viewer_user_id and self.hand and not self.hand.ended:
            seat = self._seat_of(viewer_user_id)
            if seat is not None:
                legal = self.legal_actions(seat)

        return {
            "table_id": self.table_id,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "max_seats": self.max_seats,
            "players": players_out,
            "hand": hand_out,
            "legal_actions": legal,
        }
