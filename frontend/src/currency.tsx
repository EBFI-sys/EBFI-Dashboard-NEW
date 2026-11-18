import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, money } from "./api";
import { useAuth } from "./auth";

/** Currencies the business uses. P&L figures are stored in INR and shown in any of these at the month's rate. */
export const VIEW_CURRENCIES = ["INR", "USD", "EUR", "GBP"] as const;
export type Cur = (typeof VIEW_CURRENCIES)[number];

type Ctx = {
  cur: Cur;
  setCur: (c: Cur) => void;
  /** INR amount of `month` in the chosen currency (null when there is no rate for it yet) */
  conv: (inr: number | null | undefined, month: string) => number | null;
  /** formatted amount in the chosen currency */
  fmt: (inr: number | null | undefined, month: string, compact?: boolean) => string;
  missing: (month: string) => boolean;
};
const CurCtx = createContext<Ctx>(null as unknown as Ctx);

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [cur, setCurState] = useState<Cur>(() => {
    try {
      return (localStorage.getItem("ebfi.cur") as Cur) || "INR";
    } catch {
      return "INR";
    }
  });
  const [rates, setRates] = useState<{ month: string; currency: string; rate: number }[]>([]);
  const { me } = useAuth();
  useEffect(() => {
    if (me) api.get("/fx-rates").then(setRates).catch(() => setRates([]));
  }, [me]);
  const setCur = (c: Cur) => {
    setCurState(c);
    try {
      localStorage.setItem("ebfi.cur", c);
    } catch {
      /* private window */
    }
  };
  const rateFor = useCallback((month: string, c: string) => {
    // the month's rate, else the latest earlier month (provisional), as on the server
    const list = rates.filter((r) => r.currency === c && r.month <= month).sort((a, b) => (a.month < b.month ? 1 : -1));
    return list[0]?.rate ?? null;
  }, [rates]);
  const conv = useCallback((inr: number | null | undefined, month: string) => {
    if (inr == null) return null;
    if (cur === "INR") return inr;
    const r = rateFor(month, cur);
    return r ? inr / r : null;
  }, [cur, rateFor]);
  const fmt = useCallback((inr: number | null | undefined, month: string, compact = false) => {
    const v = conv(inr, month);
    return v == null ? "—" : money(v, cur, compact);
  }, [conv, cur]);
  const missing = useCallback((month: string) => cur !== "INR" && !rateFor(month, cur), [cur, rateFor]);
  return <CurCtx.Provider value={{ cur, setCur, conv, fmt, missing }}>{children}</CurCtx.Provider>;
}

export const useCurrency = () => useContext(CurCtx);

export function CurrencySwitch() {
  const { cur, setCur } = useCurrency();
  return (
    <div className="seg" role="group" aria-label="Валюта показа">
      {VIEW_CURRENCIES.map((c) => (
        <button key={c} type="button" className={cur === c ? "on" : ""} onClick={() => setCur(c)}>{c}</button>
      ))}
    </div>
  );
}
