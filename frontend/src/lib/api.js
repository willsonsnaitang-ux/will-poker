import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

export function formatApiError(e) {
  const detail = e?.response?.data?.detail;
  if (detail == null) return e?.message || "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((x) => (x && typeof x.msg === "string" ? x.msg : JSON.stringify(x)))
      .join(" ");
  if (typeof detail === "object" && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

// WS URL: same host as backend, wss:// for https backend
export function wsUrl(path) {
  const httpBase = BACKEND_URL || "";
  const wsBase = httpBase.replace(/^http/, "ws");
  return `${wsBase}${path}`;
}
