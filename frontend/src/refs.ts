import { useEffect, useState } from "react";
import { api } from "./api";

// Small cache of reference lists used by selects across the app.
const cache: Record<string, Promise<any[]> | undefined> = {};

export function loadRef(name: string, fresh = false): Promise<any[]> {
  if (fresh || !cache[name]) cache[name] = api.get<any[]>("/" + name).catch((e) => {
    cache[name] = undefined;
    throw e;
  });
  return cache[name]!;
}

export function invalidateRef(name: string) {
  cache[name] = undefined;
}

export function useRef_(name: string): any[] {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    loadRef(name).then(setRows).catch(() => setRows([]));
  }, [name]);
  return rows;
}

export const CURRENCIES = ["USD", "EUR", "GBP", "INR"];
export const REGIONS = ["Europe", "China", "India", "USA", "Latin America & Canada", "Russia & CIS", "Middle East", "Asia-Pacific & other"];
export const JOB_STATUSES = ["В работе", "Пауза", "Завершен"];
