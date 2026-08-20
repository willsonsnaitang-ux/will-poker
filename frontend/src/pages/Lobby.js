import React, { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Users, Filter, Search } from "lucide-react";
import { toast } from "sonner";

export default function Lobby() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [stakeFilter, setStakeFilter] = useState("all"); // all | micro | low | mid | high
  const [joining, setJoining] = useState(null); // table object being joined
  const [buyIn, setBuyIn] = useState(0);

  const load = async () => {
    try {
      const { data } = await api.get("/tables");
      setTables(data);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  const filtered = useMemo(() => {
    return tables.filter((t) => {
      if (q && !t.name.toLowerCase().includes(q.toLowerCase())) return false;
      if (stakeFilter === "micro" && t.big_blind > 2) return false;
      if (stakeFilter === "low" && (t.big_blind < 5 || t.big_blind > 20)) return false;
      if (stakeFilter === "mid" && (t.big_blind < 25 || t.big_blind > 100)) return false;
      if (stakeFilter === "high" && t.big_blind < 200) return false;
      return true;
    });
  }, [tables, q, stakeFilter]);

  const openJoin = (table) => {
    setJoining(table);
    setBuyIn(table.buy_in_min);
  };

  const doJoin = async () => {
    if (!joining) return;
    try {
      await api.post(`/tables/${joining.id}/join`, { buy_in: buyIn });
      await refresh();
      nav(`/table/${joining.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="flex items-baseline justify-between mb-8 flex-wrap gap-4">
        <div>
          <h1 className="font-heading text-4xl md:text-5xl font-light tracking-tighter text-gold-soft">
            Cash Lobby
          </h1>
          <p className="text-white/50 mt-1 text-sm font-mono uppercase tracking-widest">
            No-Limit Hold&apos;em · 6-max
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
            <input
              placeholder="Search tables"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="wp-input pl-9 w-56"
              data-testid="lobby-search"
            />
          </div>
          <div className="flex items-center gap-1 rounded-full bg-white/5 border border-white/10 p-1" data-testid="stake-filter">
            {[
              { k: "all", l: "All" },
              { k: "micro", l: "Micro" },
              { k: "low", l: "Low" },
              { k: "mid", l: "Mid" },
              { k: "high", l: "High" },
            ].map((f) => (
              <button
                key={f.k}
                onClick={() => setStakeFilter(f.k)}
                className={`px-3 py-1 text-xs font-mono uppercase tracking-widest rounded-full transition-colors ${
                  stakeFilter === f.k
                    ? "bg-[var(--wp-gold)] text-[#18181B]"
                    : "text-white/60 hover:text-white"
                }`}
                data-testid={`filter-${f.k}`}
              >
                {f.l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-white/40 font-mono text-sm">Loading tables…</div>
      ) : filtered.length === 0 ? (
        <div className="text-white/40 font-mono text-sm">No tables match.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="tables-grid">
          {filtered.map((t) => (
            <div
              key={t.id}
              className="wp-panel p-5 hover:border-[var(--wp-gold)]/40 transition-colors cursor-pointer"
              onClick={() => openJoin(t)}
              data-testid={`table-card-${t.id}`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs font-mono uppercase tracking-widest text-gold">
                    {t.stakes}
                  </div>
                  <h3 className="font-heading text-2xl mt-1 text-white">{t.name}</h3>
                </div>
                <div className="flex items-center gap-1 text-white/50 text-xs font-mono">
                  <Users className="w-3.5 h-3.5" />
                  <span data-testid={`table-seated-${t.id}`}>{t.seated}/{t.max_seats}</span>
                </div>
              </div>
              <div className="mt-4 flex items-end justify-between">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-white/40">Buy-in</div>
                  <div className="font-mono text-white/90">{t.buy_in_min.toLocaleString()} – {t.buy_in_max.toLocaleString()}</div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); openJoin(t); }}
                  className="wp-btn-primary"
                  data-testid={`join-${t.id}`}
                >
                  Join
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Buy-in modal */}
      {joining && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center px-6" onClick={() => setJoining(null)}>
          <div className="wp-panel p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="buyin-modal">
            <h3 className="font-heading text-2xl text-gold-soft">Take a seat</h3>
            <p className="text-white/60 text-sm mt-1">{joining.name} · {joining.stakes}</p>
            <div className="mt-5">
              <label className="text-xs font-mono uppercase tracking-widest text-white/50">Buy-in</label>
              <input
                type="range"
                min={joining.buy_in_min}
                max={Math.min(joining.buy_in_max, user?.bankroll || 0)}
                value={buyIn}
                onChange={(e) => setBuyIn(Number(e.target.value))}
                className="w-full accent-[var(--wp-gold)] mt-2"
                data-testid="buyin-slider"
              />
              <input
                type="number"
                min={joining.buy_in_min}
                max={joining.buy_in_max}
                value={buyIn}
                onChange={(e) => setBuyIn(Number(e.target.value))}
                className="wp-input font-mono mt-2 text-center"
                data-testid="buyin-input"
              />
              <div className="mt-2 text-xs text-white/40 font-mono flex justify-between">
                <span>Min {joining.buy_in_min}</span>
                <span>Your chips: {user?.bankroll?.toLocaleString() || 0}</span>
                <span>Max {joining.buy_in_max}</span>
              </div>
            </div>
            <div className="mt-6 flex gap-3">
              <button className="wp-btn-ghost flex-1" onClick={() => setJoining(null)} data-testid="buyin-cancel">Cancel</button>
              <button
                className="wp-btn-primary flex-1"
                disabled={buyIn < joining.buy_in_min || buyIn > joining.buy_in_max || (user?.bankroll || 0) < buyIn}
                onClick={doJoin}
                data-testid="buyin-confirm"
              >
                Sit down
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
