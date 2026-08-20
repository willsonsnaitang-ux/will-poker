import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Login() {
  const { login, error } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const ok = await login(email, password);
    setBusy(false);
    if (ok) {
      toast.success("Welcome back");
      nav("/lobby");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-16">
      <div className="wp-panel p-8 w-full max-w-md" data-testid="login-form">
        <Link to="/" className="font-heading text-2xl text-white block mb-2">
          Will<span className="text-gold">Poker</span>
        </Link>
        <h1 className="font-heading text-3xl text-gold-soft tracking-tight">Log in</h1>
        <p className="text-white/50 mt-1 text-sm">Take your seat.</p>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-white/50">Email</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="wp-input mt-1"
              data-testid="login-email"
            />
          </div>
          <div>
            <label className="text-xs font-mono uppercase tracking-widest text-white/50">Password</label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="wp-input mt-1"
              data-testid="login-password"
            />
          </div>
          {error && (
            <div className="text-sm text-red-400 font-mono" data-testid="login-error">{error}</div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="wp-btn-primary w-full"
            data-testid="login-submit"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="mt-6 text-sm text-white/60 text-center">
          New here? <Link to="/signup" className="text-gold hover:text-gold-soft">Create an account</Link>
        </div>
      </div>
    </div>
  );
}
