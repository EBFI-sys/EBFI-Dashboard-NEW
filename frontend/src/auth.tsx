import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

export type Me = {
  id: number;
  name: string;
  email: string;
  initials: string;
  role: "admin" | "accountant" | "manager";
  rights: string[];
  totp_enabled: boolean;
  totp_required: boolean;
};

type Ctx = { me: Me | null; loading: boolean; setMe: (m: Me | null) => void; can: (r: string) => boolean; logout: () => void };
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<Me>("/auth/me").then(setMe).catch(() => setMe(null)).finally(() => setLoading(false));
    const out = () => setMe(null);
    window.addEventListener("ebfi:logout", out);
    return () => window.removeEventListener("ebfi:logout", out);
  }, []);

  const logout = useCallback(() => {
    api.post("/auth/logout").finally(() => setMe(null));
  }, []);

  const can = useCallback((r: string) => !!me && me.rights.includes(r), [me]);
  return <AuthCtx.Provider value={{ me, loading, setMe, can, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
