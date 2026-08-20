"""Cryptographically-secure poker deck."""
import secrets

RANKS = "23456789TJQKA"
SUITS = "shdc"  # spades, hearts, diamonds, clubs


def full_deck():
    return [r + s for r in RANKS for s in SUITS]


class Deck:
    def __init__(self, seed_log: list | None = None):
        self.cards = full_deck()
        self._shuffle()
        self.seed_log = seed_log  # optional list to append audit entries

    def _shuffle(self):
        # Fisher-Yates with cryptographic RNG
        n = len(self.cards)
        for i in range(n - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            self.cards[i], self.cards[j] = self.cards[j], self.cards[i]

    def draw(self, n=1):
        drawn = []
        for _ in range(n):
            drawn.append(self.cards.pop())
        return drawn
