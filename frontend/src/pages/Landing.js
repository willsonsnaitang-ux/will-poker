import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Zap, Shield, Trophy } from "lucide-react";

export default function Landing() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 -z-10"
          style={{
            background:
              "radial-gradient(1000px 500px at 50% 20%, rgba(27,84,54,0.35), transparent 60%)",
          }}
        />
        <div className="max-w-6xl mx-auto px-6 pt-20 pb-24 md:pt-28 md:pb-32 grid md:grid-cols-2 gap-14 items-center">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-hair bg-white/5 text-xs font-mono uppercase tracking-widest text-white/70 mb-6">
              <span className="w-1.5 h-1.5 bg-[var(--wp-emerald)] rounded-full" />
              Canada · Ontario Certified Path
            </div>
            <h1 className="font-heading text-5xl md:text-6xl lg:text-7xl font-light tracking-tighter text-gold-soft leading-[0.95]">
              Play the felt.<br />Own the moment.
            </h1>
            <p className="mt-6 text-white/70 text-lg max-w-lg leading-relaxed">
              Real-time No-Limit Hold&apos;em cash tables with a server-authoritative
              engine, cryptographic RNG, and a table that always feels alive.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link to="/signup" className="wp-btn-primary inline-flex items-center gap-2" data-testid="hero-signup-btn">
                Claim your seat <ChevronRight className="w-4 h-4" />
              </Link>
              <Link to="/login" className="wp-btn-ghost" data-testid="hero-login-btn">Already a player</Link>
            </div>
            <div className="mt-10 flex items-center gap-8 text-xs font-mono uppercase tracking-widest text-white/40">
              <span>Play money · v1</span>
              <span>KYC ready · deferred</span>
            </div>
          </div>
          <div className="relative">
            <div className="relative aspect-square rounded-full felt felt-ring overflow-hidden">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex gap-2">
                  {["Ah","Kh","Qh","Jh","Th"].map((c, i) => (
                    <div key={c} className="pcard large" style={{
                      transform: `translateY(${Math.abs(i-2)*4}px) rotate(${(i-2)*4}deg)`,
                      color: (c[1]==="h"||c[1]==="d") ? "#C81E1E" : "#18181B"
                    }}>
                      <div className="flex flex-col items-start leading-none">
                        <span className="rank">{c[0]==="T"?"10":c[0]}</span>
                        <span className="suit">{c[1]==="h"?"♥":c[1]==="d"?"♦":c[1]==="s"?"♠":"♣"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="absolute bottom-6 left-1/2 -translate-x-1/2 font-mono text-xs uppercase tracking-[0.35em] text-gold-soft/80">
                Royal Flush · 24k Pot
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 py-16 md:py-24">
        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              icon: Zap,
              t: "Real-time. Everywhere.",
              d: "WebSocket-driven game state means zero refresh, buttery smooth animations, and instant showdowns.",
            },
            {
              icon: Shield,
              t: "Server-authoritative.",
              d: "The engine — deck, shuffle, hand evaluator — runs on our servers. Your client never sees another player's cards.",
            },
            {
              icon: Trophy,
              t: "Built for the grind.",
              d: "Multi-table capable, deep hand history, and a UI made for long sessions. Tournaments arriving soon.",
            },
          ].map(({ icon: Icon, t, d }) => (
            <div key={t} className="wp-panel p-6" data-testid={`feature-${t.split(" ")[0].toLowerCase()}`}>
              <Icon className="w-6 h-6 text-gold" />
              <h3 className="font-heading text-xl mt-4 text-white">{t}</h3>
              <p className="mt-2 text-sm text-white/60 leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-hair py-8 text-center text-xs text-white/40 font-mono uppercase tracking-widest">
        © Will Poker · Play-money demo · KYC & licensing gated for real-money launch
      </footer>
    </div>
  );
}
