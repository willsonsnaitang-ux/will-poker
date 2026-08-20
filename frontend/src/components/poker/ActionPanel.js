import React, { useState, useEffect } from "react";

export default function ActionPanel({ legal, hand, onAction, disabled }) {
  const toCall = legal?.to_call || 0;
  const minRaise = legal?.min_raise_total || 0;
  const maxRaise = legal?.max_raise_total || 0;
  const canCheck = !!legal?.can_check;
  const canCall = !!legal?.can_call;
  const canRaise = !!legal?.can_bet_or_raise;
  const pot = hand?.pot || 0;
  const isRaise = toCall > 0 || (hand?.current_bet || 0) > 0;

  const [amount, setAmount] = useState(minRaise);

  useEffect(() => {
    setAmount(Math.max(minRaise, 0));
  }, [minRaise]);

  const setPreset = (target) => {
    const clamped = Math.max(minRaise, Math.min(target, maxRaise));
    setAmount(clamped);
  };

  const hasActions = canCheck || canCall || canRaise;

  if (!hasActions) {
    return (
      <div className="wp-panel px-6 py-4 flex items-center justify-center text-white/50 text-sm font-mono uppercase tracking-widest" data-testid="action-panel-waiting">
        Waiting…
      </div>
    );
  }

  return (
    <div className="wp-panel px-4 py-3 md:px-6 md:py-4" data-testid="action-panel">
      {canRaise && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1">
            {[
              { label: "Min", val: minRaise },
              { label: "½ Pot", val: Math.round(pot / 2 + toCall) },
              { label: "Pot", val: pot + toCall },
              { label: "All-in", val: maxRaise },
            ].map((p) => (
              <button
                key={p.label}
                onClick={() => setPreset(p.val)}
                className="text-[11px] font-mono uppercase px-2 py-1 rounded-md bg-white/5 border border-white/10 hover:border-[var(--wp-gold)]/50 text-white/80"
                data-testid={`preset-${p.label.toLowerCase().replace(/[^a-z]/g, "")}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <input
            type="range"
            min={minRaise}
            max={maxRaise}
            step={1}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="flex-1 min-w-[120px] accent-[var(--wp-gold)]"
            data-testid="bet-slider"
          />
          <input
            type="number"
            value={amount}
            min={minRaise}
            max={maxRaise}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="wp-input font-mono w-28 text-center"
            data-testid="bet-input"
          />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          disabled={disabled}
          onClick={() => onAction("fold")}
          className="flex-1 min-w-[80px] py-3 rounded-xl bg-[#27272A] text-white/70 border border-white/10 hover:bg-[#333338] font-heading uppercase tracking-widest text-sm disabled:opacity-40"
          data-testid="fold-button"
        >
          Fold
        </button>
        {canCheck ? (
          <button
            disabled={disabled}
            onClick={() => onAction("check")}
            className="flex-1 min-w-[80px] py-3 rounded-xl bg-[#3A3A40] text-white border border-white/10 hover:brightness-110 font-heading uppercase tracking-widest text-sm disabled:opacity-40"
            data-testid="check-button"
          >
            Check
          </button>
        ) : (
          <button
            disabled={disabled || !canCall}
            onClick={() => onAction("call")}
            className="flex-1 min-w-[80px] py-3 rounded-xl bg-[#3A3A40] text-white border border-white/10 hover:brightness-110 font-heading uppercase tracking-widest text-sm disabled:opacity-40"
            data-testid="call-button"
          >
            Call <span className="font-mono ml-1 text-gold-soft">{toCall.toLocaleString()}</span>
          </button>
        )}
        <button
          disabled={disabled || !canRaise || minRaise <= 0 || amount < minRaise}
          onClick={() => onAction(isRaise ? "raise" : "bet", amount)}
          className="flex-1 min-w-[100px] py-3 rounded-xl wp-btn-primary font-heading uppercase tracking-widest text-sm disabled:opacity-40"
          data-testid="raise-button"
        >
          {isRaise ? "Raise to" : "Bet"} <span className="font-mono ml-1">{amount.toLocaleString()}</span>
        </button>
      </div>
    </div>
  );
}
