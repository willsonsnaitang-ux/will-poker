import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { LogOut, User, Shield, Home } from "lucide-react";

export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-40 border-b border-hair bg-[rgba(10,10,11,0.75)] backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/lobby" className="flex items-center gap-2 group" data-testid="brand-link">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--wp-gold)] to-[var(--wp-gold-dark)] flex items-center justify-center text-[#18181B] font-heading font-bold">
            W
          </div>
          <span className="font-heading text-xl tracking-tight text-white group-hover:text-gold-soft transition-colors">
            Will<span className="text-gold">Poker</span>
          </span>
        </Link>
        <nav className="flex items-center gap-4">
          {user && typeof user === "object" && (
            <>
              <Link
                to="/lobby"
                className="text-sm text-white/70 hover:text-white flex items-center gap-1.5"
                data-testid="nav-lobby"
              >
                <Home className="w-4 h-4" /> Lobby
              </Link>
              <Link
                to="/profile"
                className="text-sm text-white/70 hover:text-white flex items-center gap-1.5"
                data-testid="nav-profile"
              >
                <User className="w-4 h-4" /> Profile
              </Link>
              {user.role === "admin" && (
                <Link
                  to="/admin"
                  className="text-sm text-white/70 hover:text-white flex items-center gap-1.5"
                  data-testid="nav-admin"
                >
                  <Shield className="w-4 h-4" /> Admin
                </Link>
              )}
              <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
                <span className="text-xs font-mono uppercase tracking-widest text-white/50">Chips</span>
                <span className="font-mono text-gold-soft" data-testid="header-bankroll">
                  {user.bankroll.toLocaleString()}
                </span>
              </div>
              <button
                onClick={async () => { await logout(); navigate("/"); }}
                className="text-white/60 hover:text-white"
                data-testid="logout-btn"
                aria-label="Log out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
