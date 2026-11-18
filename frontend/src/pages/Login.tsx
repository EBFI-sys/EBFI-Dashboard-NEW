import { useState } from "react";
import { api } from "../api";
import { Me, useAuth } from "../auth";

export default function Login() {
  const { setMe } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      setMe(await api.post<Me>("/auth/login", { email, password, code: code || null }));
    } catch (e: any) {
      if (e.message.includes("код")) setNeedCode(true);
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-mark">EBFI</div>
        <h1>EBFI Ops</h1>
        <p className="muted">Заявки, работы, инвойсы и выплаты инспекторам</p>
        <label className="field">
          <span>Email</span>
          <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="field">
          <span>Пароль</span>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {needCode && (
          <label className="field">
            <span>Код из приложения-аутентификатора</span>
            <input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} autoFocus />
          </label>
        )}
        {err && <p className="error">{err}</p>}
        <button className="btn primary block" disabled={busy}>{busy ? "Вхожу…" : "Войти"}</button>
      </form>
    </div>
  );
}
