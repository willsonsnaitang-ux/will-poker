"""A player who sits down while a hand is in progress must NOT be treated as
part of that hand (they have no hole cards)."""
import sys

sys.path.insert(0, "/app/backend")

from poker.game import PokerGame  # noqa: E402


def test_player_seated_midhand_is_not_dealt_into_current_hand():
    g = PokerGame("t", 5, 10, 6)
    g.sit("u1", "p1", 0, 500)
    g.sit("u2", "p2", 1, 500)
    g.start_hand()
    # third player buys in mid-hand
    g.sit("u3", "p3", 2, 500)
    late = g.seats[2]
    assert late.hole_cards == [], "late joiner should have no cards"
    assert late.folded is True, (
        "BUG: mid-hand joiner has folded=False, so the engine treats a player with no "
        "hole cards as live in the current hand (can be given action / reach showdown)"
    )
    # engine must never hand action to the cardless player
    actor = g.seats[g.hand.to_act].user_id
    g.act(actor, "call")
    while g.hand and not g.hand.ended and g.hand.to_act is not None:
        seat = g.hand.to_act
        assert g.seats[seat].hole_cards, (
            f"seat {seat} was given action with no hole cards"
        )
        legal = g.legal_actions(seat)
        g.act(g.seats[seat].user_id, "check" if legal.get("can_check") else "call")
