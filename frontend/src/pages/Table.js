import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatApiError, wsUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Card from "@/components/poker/Card";
import Seat from "@/components/poker/Seat";
import ActionPanel from "@/components/poker/ActionPanel";
import { toast } from "sonner";
import { MessageSquare, LogOut } from "lucide-react";

const TURN_TIMEOUT = 25;

const HAND_NAMES = {
  HIGH_CARD: "High Card", PAIR: "Pair", TWO_PAIR: "Two Pair",
  THREE_OF_A_KIND: "Three of a Kind", STRAIGHT: "Straight", FLUSH: "Flush",
  FULL_HOUSE: "Full House", FOUR_OF_A_KIND: "Four of a Kind",
  STRAIGHT_FLUSH: "Straight Flush", ROYAL_FLUSH: "Royal Flush",
};

const prettyHand = (h) =>
  !h ? "" : HAND_NAMES[String(h).toUpperCase()] ||
    String(h).replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

export default function TablePage() {
  const { tableId } = useParams();
  const nav = useNavigate();
  const { user, refresh } = useAuth();
  const [state, setState] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatText, setChatText] = useState("");
  const [connected, setConnected] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const [tick, setTick] = useState(0);

  // periodic tick for the turn timer UI
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 200);
    return () => clearInterval(id);
  }, []);

  const connect = useCallback(async () => {
    if (!user) return;
    // get token via /auth/me not needed; cookies used server-side.
    // For WS we need a JWT in query. We'll request a short-lived token.
    // Simpler: reuse access_token cookie? Cookies aren't sent on same-origin WS across schemes in preview.
    // We embed the token by having the server issue it via a helper endpoint.
    let token;
    try {
      const { data } = await api.post("/auth/ws-token", {});
      token = data.token;
    } catch (e) {
      // fallback: some browsers do send cookies over WS same origin; try without token
      token = "";
    }
    const url = wsUrl(`/api/ws/table/${tableId}?token=${encodeURIComponent(token || "")}`);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") setState(msg.state);
        else if (msg.type === "error") toast.error(msg.message);
      } catch {}
    };
    ws.onclose = () => {
      setConnected(false);
      if (reconnectRef.current) return;
      reconnectRef.current = setTimeout(() => {
        reconnectRef.current = null;
        connect();
      }, 1500);
    };
    ws.onerror = () => { try { ws.close(); } catch {} };
  }, [tableId, user]);

  useEffect(() => {
    connect();
    return () => {
      try { wsRef.current?.close(); } catch {}
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [connect]);

  const send = (obj) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  };

  const doAction = (action, amount = 0) => {
    send({ type: "action", action, amount });
  };

  const leave = async () => {
    if (leaving) return;
    setLeaving(true);
    try {
      await api.post(`/tables/${tableId}/leave`, {}, { timeout: 10000 });
      await refresh();
      nav("/lobby");
    } catch (e) {
      toast.error(formatApiError(e));
      setLeaving(false);
    }
  };

  const heroSeat = useMemo(() => {
    if (!state || !user) return null;
    return state.players.find((p) => p.user_id === user.id)?.seat ?? null;
  }, [state, user]);

  // rotate seats so hero appears at seat 0 (bottom)
  const rotatedPlayers = useMemo(() => {
    if (!state) return [];
    const max = state.max_seats;
    const offset = heroSeat != null ? heroSeat : 0;
    // map: display_seat = (seat - offset + max) % max
    const bySeat = {};
    for (const p of state.players) {
      const disp = (p.seat - offset + max) % max;
      bySeat[disp] = p;
    }
    return { bySeat, offset };
  }, [state, heroSeat]);

  const dealerDisp = useMemo(() => {
    if (!state?.hand || heroSeat == null) return null;
    return (state.hand.dealer_seat - (heroSeat ?? 0) + state.max_seats) % state.max_seats;
  }, [state, heroSeat]);

  const toActDisp = useMemo(() => {
    if (!state?.hand?.to_act && state?.hand?.to_act !== 0) return null;
    if (heroSeat == null) return null;
    return (state.hand.to_act - (heroSeat ?? 0) + state.max_seats) % state.max_seats;
  }, [state, heroSeat]);

  const turnPct = useMemo(() => {
    if (!state?.turn_deadline) return null;
    const now = Date.now() / 1000;
    const remain = state.turn_deadline - now;
    return Math.max(0, Math.min(1, remain / TURN_TIMEOUT));
  }, [state, tick]);

  const nextHandIn = useMemo(() => {
    if (!state?.next_hand_at) return null;
    const remain = Math.ceil(state.next_hand_at - Date.now() / 1000);
    return remain > 0 ? remain : 0;
  }, [state, tick]);

  if (!state) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-white/40 font-mono">
        Connecting to table…
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 pt-2 pb-6 min-h-[calc(100vh-140px)] flex flex-col justify-center" data-testid="poker-table-page">
      {/* Header row */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-gold">
            {state.meta.stakes}
          </div>
          <h1 className="font-heading text-2xl md:text-3xl text-white" data-testid="table-name">{state.meta.name}</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${connected ? "bg-[var(--wp-emerald)]" : "bg-red-500"}`} title={connected ? "Live" : "Reconnecting"} />
          <button className="wp-btn-ghost" onClick={() => setChatOpen((v) => !v)} data-testid="chat-toggle">
            <MessageSquare className="w-4 h-4" />
          </button>
          <button className="wp-btn-ghost inline-flex items-center gap-1 disabled:opacity-50" onClick={leave} disabled={leaving} data-testid="leave-btn">
            <LogOut className="w-4 h-4" /> {leaving ? "Leaving…" : "Leave"}
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="relative mx-auto w-full" style={{ maxWidth: 900 }}>
        <div className="relative felt felt-ring rounded-[999px]" style={{ aspectRatio: "2 / 1" }} data-testid="poker-table">
          {/* Community cards + pot */}
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pb-20">
            <div className="flex gap-2" data-testid="community-cards">
              {Array.from({ length: 5 }).map((_, i) => {
                const c = state.hand?.board?.[i];
                return c ? <Card key={i} card={c} large /> : (
                  <div key={i} className="pcard large" style={{ opacity: 0.08, background: "#000", border: "1px dashed rgba(255,255,255,0.15)" }} />
                );
              })}
            </div>
            <div className="mt-2 px-4 py-1 rounded-full bg-black/60 border border-white/10">
              <span className="text-[10px] font-mono uppercase tracking-widest text-white/50 mr-2">Pot</span>
              <span className="font-mono text-gold-soft" data-testid="pot-amount">
                {(state.hand?.ended
                  ? (state.hand.winners || []).reduce((s, w) => s + w.amount, 0)
                  : state.hand?.pot || 0
                ).toLocaleString()}
              </span>
            </div>
            {state.hand?.ended && state.hand.winners?.length > 0 && (
              <div className="mt-2 px-4 py-1.5 max-w-[85%] text-center rounded-lg bg-black/75 border border-[var(--wp-gold)]/40 text-[11px] md:text-xs font-mono uppercase tracking-widest text-gold leading-relaxed" data-testid="winner-banner">
                {state.hand.winners
                  .map((w) => {
                    const name =
                      w.username ||
                      state.players.find((p) => p.user_id === w.user_id)?.username ||
                      "Player";
                    return `${name} wins ${w.amount.toLocaleString()}${w.hand ? " · " + prettyHand(w.hand) : ""}`;
                  })
                  .join(" · ")}
              </div>
            )}
            {state.hand?.ended && nextHandIn != null && (
              <div className="text-[10px] font-mono uppercase tracking-widest text-white/50" data-testid="next-hand-countdown">
                Next hand in {nextHandIn}s
              </div>
            )}
            {!state.hand && (
              <div className="mt-2 text-xs font-mono uppercase tracking-widest text-white/50">
                Waiting for players…
              </div>
            )}
          </div>

          {/* Seats */}
          {Array.from({ length: state.max_seats }).map((_, dispSeat) => {
            const p = rotatedPlayers.bySeat?.[dispSeat];
            const isTurn = toActDisp === dispSeat && state.hand && !state.hand.ended;
            const isDealer = dealerDisp === dispSeat && state.hand;
            const isHero = p && user && p.user_id === user.id;
            return (
              <Seat
                key={dispSeat}
                seat={dispSeat}
                player={p}
                isHero={isHero}
                isTurn={isTurn}
                dealer={isDealer}
                turnPct={isTurn ? turnPct : null}
                maxSeats={state.max_seats}
              />
            );
          })}
        </div>
      </div>

      {/* Action Panel */}
      <div className="max-w-3xl w-full mx-auto mt-8">
        <ActionPanel
          legal={state.legal_actions}
          hand={state.hand}
          onAction={doAction}
        />
      </div>

      {/* Hand info bar */}
      <div className="max-w-3xl w-full mx-auto mt-3 flex justify-between text-[11px] font-mono uppercase tracking-widest text-white/40">
        <span>Hand #{state.hand?.hand_number || "—"}</span>
        <span>Street: {state.hand?.street || "—"}</span>
        <span>Min raise: {state.hand?.min_raise?.toLocaleString() || "—"}</span>
      </div>

      {/* Chat */}
      {chatOpen && (
        <div className="fixed right-4 bottom-4 z-40 w-80 wp-panel p-3" data-testid="chat-panel">
          <div className="text-xs font-mono uppercase tracking-widest text-white/50 mb-2">Table Chat</div>
          <div className="h-48 overflow-y-auto scrollbar-thin space-y-1">
            {(state.chat || []).map((c, i) => (
              <div key={i} className="text-sm">
                <span className="text-gold-soft font-mono text-[11px]">{c.username}:</span>{" "}
                <span className="text-white/80">{c.text}</span>
              </div>
            ))}
            {(!state.chat || state.chat.length === 0) && (
              <div className="text-white/30 text-sm italic">No messages yet.</div>
            )}
          </div>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (chatText.trim()) {
                send({ type: "chat", text: chatText.trim() });
                setChatText("");
              }
            }}
          >
            <input
              value={chatText}
              onChange={(e) => setChatText(e.target.value)}
              placeholder="Type a message"
              className="wp-input"
              data-testid="chat-input"
            />
            <button className="wp-btn-primary" type="submit" data-testid="chat-send">Send</button>
          </form>
        </div>
      )}
    </div>
  );
}
