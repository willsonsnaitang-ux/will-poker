import React from "react";

const SUIT_MAP = {
  s: { char: "♠", red: false },
  c: { char: "♣", red: false },
  h: { char: "♥", red: true },
  d: { char: "♦", red: true },
};

// card: string like "Ah" | "Ts" | "?"  (or "?" for back)
export default function Card({ card, large = false, back = false, testid }) {
  if (back || !card || card === "?" || card === "??") {
    return (
      <div className={`pcard back ${large ? "large" : ""}`} data-testid={testid}>
        &nbsp;
      </div>
    );
  }
  const rank = card[0] === "T" ? "10" : card[0];
  const suit = SUIT_MAP[card[1]] || { char: "?", red: false };
  return (
    <div
      className={`pcard ${large ? "large" : ""} ${suit.red ? "red" : ""}`}
      data-testid={testid}
    >
      <div className="flex flex-col items-start leading-none">
        <span className="rank">{rank}</span>
        <span className="suit">{suit.char}</span>
      </div>
    </div>
  );
}
