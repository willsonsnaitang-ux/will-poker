import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Signup() {
  const { register, error } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const ok = await register(email, password, username);
    setBusy(false);
    if (ok) {
      toast.success("Welcome to Will Poker · 10,000 chips granted");
      nav("/lobby");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-16">
      <div className="wp-panel p-8 w-full max-w-md" data-testid="signup-form">
        <Link to="/" className="font-heading text-2xl text-white block mb-2">
          Will<span className="text-gold">Poker</span>
        </Link>
        <h1 className="font-heading text-3xl text-gold-soft tracking-tight">Sign up</h1>
        <p className="text-white/50 mt-1 text-sm">Free 10,000 play-money chips on us.</p>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-white/50">Username</label>
            <input
              required minLength={3} maxLength={20}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="wp-input mt-1"
              data-testid="signup-username"
            />
          </div>
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-white/50">Email</label>
            <input
              type="email" required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="wp-input mt-1"
              data-testid="signup-email"
            />
          </div>
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-white/50">Password</label>
            <input
              type="password" required minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="wp-input mt-1"
              data-testid="signup-password"
            />
          </div>
          {error && (
            <div className="text-sm text-red-400 font-mono" data-testid="signup-error">{error}</div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="wp-btn-primary w-full"
            data-testid="signup-submit"
          >
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
        <div className="mt-6 text-sm text-white/60 text-center">
          Already have an account? <Link to="/login" className="text-gold hover:text-gold-soft">Log in</Link>
        </div>
      </div>
    </div>
  );
}
