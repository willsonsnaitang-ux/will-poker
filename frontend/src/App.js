import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Header from "@/components/Header";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Lobby from "@/pages/Lobby";
import TablePage from "@/pages/Table";
import Profile from "@/pages/Profile";
import Admin from "@/pages/Admin";

function Protected({ children, admin = false }) {
  const { user } = useAuth();
  if (user === null) return <div className="p-10 text-white/40 font-mono">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/lobby" replace />;
  return children;
}

function Shell() {
  const { user } = useAuth();
  return (
    <>
      {user && typeof user === "object" && <Header />}
      <Routes>
        <Route path="/" element={user && typeof user === "object" ? <Navigate to="/lobby" replace /> : <Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/lobby" element={<Protected><Lobby /></Protected>} />
        <Route path="/table/:tableId" element={<Protected><TablePage /></Protected>} />
        <Route path="/profile" element={<Protected><Profile /></Protected>} />
        <Route path="/admin" element={<Protected admin><Admin /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
        <Toaster theme="dark" position="top-right" richColors closeButton />
      </AuthProvider>
    </BrowserRouter>
  );
}
