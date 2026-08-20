import React, { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function Admin() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(25);

  const load = async () => {
    try {
      const [s, u] = await Promise.all([api.get("/admin/stats"), api.get("/admin/users", { params: { limit: 1000 } })]);
      setStats(s.data); setUsers(u.data);
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const filtered = users.filter((u) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (u.username || "").toLowerCase().includes(q) || (u.email || "").toLowerCase().includes(q);
  });
  const visible = filtered.slice(0, shown);

  const adjust = async (userId, delta) => {
    setBusy(true);
    try {
      await api.post("/admin/bankroll", { user_id: userId, delta, reason: "manual" });
      toast.success(`Adjusted ${delta > 0 ? "+" : ""}${delta}`);
      await load();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };

  if (error) return <div className="p-10 text-red-400 font-mono text-sm" data-testid="admin-error">{error}</div>;
  return (
    <div className="max-w-6xl mx-auto px-6 py-10" data-testid="admin-page">
      <h1 className="font-heading text-4xl text-gold-soft tracking-tighter">Admin</h1>
      <p className="text-white/50 mt-1 text-sm font-mono uppercase tracking-widest">Control tower</p>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8" data-testid="admin-stats">
          {[
            { l: "Users", v: stats.users, t: "users" },
            { l: "Hands", v: stats.hands, t: "hands" },
            { l: "Tables", v: stats.tables, t: "tables" },
            { l: "Active seats", v: stats.active_players, t: "active" },
          ].map((s) => (
            <div key={s.l} className="wp-panel p-5" data-testid={`admin-stat-${s.t}`}>
              <div className="text-[10px] font-mono uppercase tracking-widest text-white/50">{s.l}</div>
              <div className="font-mono text-3xl text-gold-soft mt-1">{s.v}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end justify-between mt-12 mb-4 gap-4">
        <h2 className="font-heading text-2xl text-white">Users</h2>
        <input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setShown(25); }}
          placeholder="Search username or email"
          className="wp-input max-w-xs"
          data-testid="admin-user-search"
        />
      </div>
      <div className="wp-panel overflow-hidden">
        <table className="w-full text-sm" data-testid="admin-users-table">
          <thead>
            <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-white/50 border-b border-hair">
              <th className="px-4 py-3">Username</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3 text-right">Bankroll</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((u) => (
              <tr key={u.id} className="border-b border-hair/60">
                <td className="px-4 py-3 text-white">{u.username}</td>
                <td className="px-4 py-3 text-white/60">{u.email}</td>
                <td className="px-4 py-3 text-white/70 uppercase text-xs font-mono">{u.role}</td>
                <td className="px-4 py-3 text-right font-mono text-gold-soft">{u.bankroll.toLocaleString()}</td>
                <td className="px-4 py-3 text-right">
                  <button disabled={busy} onClick={() => adjust(u.id, 5000)} className="wp-btn-ghost mr-2 text-xs" data-testid={`grant-${u.id}`}>+5,000</button>
                  <button disabled={busy} onClick={() => adjust(u.id, -1000)} className="wp-btn-ghost text-xs" data-testid={`deduct-${u.id}`}>-1,000</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center justify-between px-4 py-3 text-[11px] font-mono uppercase tracking-widest text-white/40">
          <span data-testid="admin-user-count">{visible.length} / {filtered.length} users</span>
          {visible.length < filtered.length && (
            <button className="wp-btn-ghost text-xs" onClick={() => setShown((s) => s + 25)} data-testid="admin-load-more">Load more</button>
          )}
        </div>
      </div>
    </div>
  );
}
