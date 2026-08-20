import React, { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Card from "@/components/poker/Card";

export default function Profile() {
  const { user } = useAuth();
  const [hands, setHands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/hands/mine");
        setHands(data);
      } catch (e) { setError(formatApiError(e)); }
      finally { setLoading(false); }
    })();
  }, []);

  if (!user || typeof user !== "object") return null;

  const played = hands.length;
  const wins = hands.filter((h) => (h.winners || []).some((w) => w.user_id === user.id)).length;

  return (
    <div className="max-w-5xl mx-auto px-6 py-10" data-testid="profile-page">
      <div className="flex items-center gap-5 mb-8">
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-[var(--wp-gold)] to-[var(--wp-gold-dark)] flex items-center justify-center font-heading text-3xl text-[#18181B]">
          {user.username.slice(0, 2).toUpperCase()}
        </div>
        <div>
          <h1 className="font-heading text-4xl text-gold-soft tracking-tighter">{user.username}</h1>
          <p className="text-white/50 text-sm font-mono">{user.email}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-10">
        {[
          { l: "Bankroll", v: user.bankroll.toLocaleString(), t: "bankroll" },
          { l: "Hands played", v: played, t: "played" },
          { l: "Hands won", v: wins, t: "wins" },
        ].map((s) => (
          <div key={s.l} className="wp-panel p-5" data-testid={`stat-${s.t}`}>
            <div className="text-[10px] font-mono uppercase tracking-widest text-white/50">{s.l}</div>
            <div className="font-mono text-3xl text-gold-soft mt-1">{s.v}</div>
          </div>
        ))}
      </div>

      <h2 className="font-heading text-2xl text-white mb-4">Recent hands</h2>
      {loading ? (
        <div className="text-white/40 font-mono">Loading…</div>
      ) : error ? (
        <div className="text-red-400 font-mono text-sm">{error}</div>
      ) : hands.length === 0 ? (
        <div className="wp-panel p-6 text-white/50 text-sm">No hands played yet. Join a table to start.</div>
      ) : (
        <div className="space-y-3" data-testid="hand-history">
          {hands.slice(0, 20).map((h) => {
            const won = (h.winners || []).find((w) => w.user_id === user.id);
            return (
              <div key={h.id} className="wp-panel p-4 flex items-center justify-between" data-testid={`hand-${h.id}`}>
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-white/40">Hand #{h.hand_number}</div>
                  <div className="flex gap-1 mt-2">
                    {(h.board || []).map((c, i) => <Card key={i} card={c} />)}
                  </div>
                </div>
                <div className="text-right">
                  {won ? (
                    <div>
                      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--wp-emerald)]">Won</div>
                      <div className="font-mono text-gold-soft text-xl">+{won.amount.toLocaleString()}</div>
                      {won.hand && <div className="text-[10px] font-mono text-white/50 uppercase">{won.hand.replace(/_/g, " ")}</div>}
                    </div>
                  ) : (
                    <div>
                      <div className="text-[10px] font-mono uppercase tracking-widest text-white/40">Lost</div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
