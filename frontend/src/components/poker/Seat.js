import React from "react";
import Card from "./Card";

// Seat positions around an oval (6-max), percentages relative to table container
const POSITIONS_6 = [
  { top: "82%", left: "50%" },   // 0 - bottom (hero)
  { top: "70%", left: "12%" },   // 1 - bottom-left
  { top: "18%", left: "12%" },   // 2 - top-left
  { top: "-6%", left: "50%" },   // 3 - top
  { top: "18%", left: "88%" },   // 4 - top-right
  { top: "70%", left: "88%" },   // 5 - bottom-right
];

export function seatPosition(seat, maxSeats = 6) {
  return POSITIONS_6[seat % 6];
}

export default function Seat({ seat, player, isHero, isTurn, dealer, turnPct, maxSeats }) {
  const pos = seatPosition(seat, maxSeats);
  if (!player) {
    return (
      <div
        className="absolute -translate-x-1/2 -translate-y-1/2"
        style={{ top: pos.top, left: pos.left }}
        data-testid={`seat-${seat}`}
      >
        <div
          className="w-24 h-24 rounded-full border border-dashed border-white/15 flex items-center justify-center text-[10px] font-mono text-white/40 hover:border-[var(--wp-gold)]/60"
          data-testid={`seat-${seat}-empty`}
        >
          SEAT {seat + 1}
        </div>
      </div>
    );
  }

  const ringClass = player.folded
    ? "seat-ring-folded"
    : isTurn
    ? "seat-ring-active"
    : "seat-ring-idle";

  const initial = (player.username || "?").slice(0, 2).toUpperCase();

  return (
    <div
      className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1"
      style={{ top: pos.top, left: pos.left }}
      data-testid={`seat-${seat}`}
    >
      <div className="relative">
        {/* Timer ring */}
        {isTurn && turnPct != null && (
          <svg
            className="absolute inset-0 pointer-events-none"
            width="92" height="92" viewBox="0 0 92 92"
            style={{ top: -4, left: -4 }}
          >
            <circle
              className="turn-ring"
              cx="46" cy="46" r="44"
              strokeDasharray={2 * Math.PI * 44}
              strokeDashoffset={2 * Math.PI * 44 * (1 - turnPct)}
            />
          </svg>
        )}
        <div
          className={`w-[84px] h-[84px] rounded-full ${ringClass} bg-gradient-to-br from-[#2a2a2e] to-[#141416] flex items-center justify-center font-heading text-2xl text-white/90`}
        >
          {initial}
        </div>
        {dealer && (
          <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-white text-[#18181B] text-xs font-bold flex items-center justify-center border border-black/30" data-testid={`dealer-btn-${seat}`}>D</div>
        )}
        {/* Hole cards */}
        {player.hole_cards?.length > 0 && (
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 flex gap-0.5" data-testid={`seat-${seat}-cards`}>
            {player.hole_cards.map((c, i) => (
              <div key={i} style={{ transform: `rotate(${i === 0 ? -6 : 6}deg)` }}>
                <Card card={c} back={c === "?"} />
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="text-center mt-1">
        <div className="text-xs text-white/80 font-medium max-w-[100px] truncate">
          {player.username}
        </div>
        <div className="mt-0.5 px-2 py-0.5 rounded-md bg-black/70 border border-white/10 font-mono text-[11px] text-gold-soft" data-testid={`seat-${seat}-stack`}>
          {player.stack.toLocaleString()}
        </div>
        {player.last_action && (
          <div className="mt-0.5 text-[10px] font-mono uppercase tracking-widest text-white/50">
            {player.last_action}
          </div>
        )}
      </div>
      {/* Bet chips in front of the seat */}
      {player.bet > 0 && (
        <div className="absolute" style={{
          top: seat < 3 ? "110%" : "-40%",
          left: "50%",
          transform: "translateX(-50%)",
        }} data-testid={`seat-${seat}-bet`}>
          <div className="flex items-center gap-1 bg-black/70 border border-white/10 px-2 py-0.5 rounded-full">
            <div className="chip" style={{ width: 14, height: 14 }} />
            <span className="font-mono text-[11px] text-gold-soft">{player.bet.toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}
