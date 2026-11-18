export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch("/api" + url, init);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    if (res.status === 401 && !url.startsWith("/auth/")) window.dispatchEvent(new Event("ebfi:logout"));
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export const api = {
  get: <T = any>(url: string) => call<T>("GET", url),
  post: <T = any>(url: string, body?: unknown) => call<T>("POST", url, body ?? {}),
  patch: <T = any>(url: string, body: unknown) => call<T>("PATCH", url, body),
  put: <T = any>(url: string, body: unknown) => call<T>("PUT", url, body),
  del: <T = any>(url: string) => call<T>("DELETE", url),
};

// ---------------------------------------------------------------- formatting
export const inr = (v: number | null | undefined) =>
  v == null ? "—" : (v < 0 ? "−" : "") + "₹" + Math.round(Math.abs(v)).toLocaleString("en-IN");

export const crore = (v: number | null | undefined) => {
  if (v == null) return "—";
  const a = Math.abs(v), s = v < 0 ? "−" : "";
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)} L`;
  return `${s}₹${Math.round(a).toLocaleString("en-IN")}`;
};

const SYM: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };
export const money = (v: number | null | undefined, cur = "INR", compact = false) => {
  if (v == null) return "—";
  if (cur === "INR") return compact ? crore(v) : inr(v);
  const a = Math.abs(v), s = v < 0 ? "−" : "";
  if (compact && a >= 1e6) return `${s}${SYM[cur] ?? ""}${(a / 1e6).toFixed(2)}M`;
  if (compact && a >= 1e4) return `${s}${SYM[cur] ?? ""}${(a / 1e3).toFixed(1)}k`;
  return `${s}${SYM[cur] ?? cur + " "}${Math.round(a).toLocaleString("en-US")}`;
};

export const num = (v: number | null | undefined, d = 0) =>
  v == null ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
export const monthLabel = (m: string) => {
  const [y, mm] = m.split("-");
  return `${MONTHS[Number(mm) - 1]} ${y}`;
};

export const dateLabel = (d: string | null | undefined) => {
  if (!d) return "—";
  const [y, m, dd] = d.slice(0, 10).split("-");
  return `${dd}.${m}.${y}`;
};

export const thisMonth = () => new Date().toISOString().slice(0, 7);

export function downloadCsv(name: string, rows: Record<string, unknown>[], cols: { key: string; label: string }[]) {
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const text = "﻿" + [cols.map((c) => esc(c.label)).join(";"), ...rows.map((r) => cols.map((c) => esc(r[c.key])).join(";"))].join("\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
