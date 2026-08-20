"""5-from-7 Texas Hold'em hand evaluator.

Returns a tuple ranking where higher is better. First element is category
0..8 (HIGH_CARD..STRAIGHT_FLUSH), followed by kicker ranks.
"""
from itertools import combinations

RANK_VALUES = {r: i for i, r in enumerate("23456789TJQKA", start=2)}
CATEGORIES = [
    "HIGH_CARD", "PAIR", "TWO_PAIR", "TRIPS", "STRAIGHT",
    "FLUSH", "FULL_HOUSE", "QUADS", "STRAIGHT_FLUSH"
]


def _card_rank(c):
    return RANK_VALUES[c[0]]


def _card_suit(c):
    return c[1]


def _straight_high(sorted_desc_ranks):
    """Given descending unique ranks, return high card of best straight or None."""
    ranks = sorted(set(sorted_desc_ranks), reverse=True)
    # Wheel handling: A can be low
    if 14 in ranks:
        ranks_with_wheel = ranks + [1]
    else:
        ranks_with_wheel = ranks
    for i in range(len(ranks_with_wheel) - 4):
        window = ranks_with_wheel[i:i + 5]
        if window[0] - window[4] == 4 and len(set(window)) == 5:
            return window[0]
    return None


def _rank_five(cards):
    """Rank a 5-card hand. Returns tuple with category as first element."""
    ranks = sorted([_card_rank(c) for c in cards], reverse=True)
    suits = [_card_suit(c) for c in cards]
    is_flush = len(set(suits)) == 1
    straight_hi = _straight_high(ranks)

    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    # sort by (count desc, rank desc)
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    counts_desc = [c for _, c in groups]
    ranks_by_count = [r for r, _ in groups]

    if is_flush and straight_hi:
        return (8, straight_hi)
    if counts_desc[0] == 4:
        return (7, ranks_by_count[0], ranks_by_count[1])
    if counts_desc[0] == 3 and counts_desc[1] >= 2:
        return (6, ranks_by_count[0], ranks_by_count[1])
    if is_flush:
        return (5, *ranks)
    if straight_hi:
        return (4, straight_hi)
    if counts_desc[0] == 3:
        return (3, ranks_by_count[0], *[r for r in ranks if r != ranks_by_count[0]][:2])
    if counts_desc[0] == 2 and counts_desc[1] == 2:
        high_pair = max(ranks_by_count[0], ranks_by_count[1])
        low_pair = min(ranks_by_count[0], ranks_by_count[1])
        kicker = max(r for r in ranks if r != high_pair and r != low_pair)
        return (2, high_pair, low_pair, kicker)
    if counts_desc[0] == 2:
        pair = ranks_by_count[0]
        kickers = [r for r in ranks if r != pair][:3]
        return (1, pair, *kickers)
    return (0, *ranks)


def best_hand(seven_cards):
    """Return (rank_tuple, best_five_cards) for the best 5-card combo."""
    best_rank = None
    best_five = None
    for combo in combinations(seven_cards, 5):
        r = _rank_five(list(combo))
        if best_rank is None or r > best_rank:
            best_rank = r
            best_five = list(combo)
    return best_rank, best_five


def category_name(rank_tuple):
    return CATEGORIES[rank_tuple[0]]
