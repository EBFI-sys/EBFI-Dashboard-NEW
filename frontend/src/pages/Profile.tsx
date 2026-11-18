import { useState } from "react";
import { api } from "../api";
import { Me, useAuth } from "../auth";
import { ErrorLine, Toast } from "../components/ui";

export default function Profile() {
  const { me, setMe } = useAuth();
  const [pw, setPw] = useState({ old_password: "", new_password: "" });
  const [setup, setSetup] = useState<{ secret: string } | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  if (!me) return null;

  return (
    <div className="page">
      <header className="page-head"><h1>Профиль</h1></header>
      <div className="grid2">
        <section className="card">
          <h2>Смена пароля</h2>
          <form className="form-grid" onSubmit={async (e) => {
            e.preventDefault();
            setErr(null);
            try { await api.post("/auth/password", pw); setPw({ old_password: "", new_password: "" }); setToast("Пароль изменён"); } catch (e: any) { setErr(e.message); }
          }}>
            <label className="field wide"><span>Текущий пароль</span><input type="password" autoComplete="current-password" value={pw.old_password} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} /></label>
            <label className="field wide"><span>Новый пароль (не короче 10 символов)</span><input type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></label>
            <div className="form-actions wide"><button className="btn primary">Сменить пароль</button></div>
          </form>
        </section>
        <section className="card">
          <h2>Двухфакторная аутентификация</h2>
          {me.totp_enabled ? <p>Включена. При входе нужен код из приложения.</p> : !setup ? (
            <>
              <p>Защищает вход кодом из Google Authenticator или аналогичного приложения.{me.totp_required && " Для вашей роли она обязательна."}</p>
              <button className="btn primary" onClick={async () => { setErr(null); try { setSetup(await api.post("/auth/totp/setup")); } catch (e: any) { setErr(e.message); } }}>Включить</button>
            </>
          ) : (
            <form className="form-grid" onSubmit={async (e) => {
              e.preventDefault();
              setErr(null);
              try { setMe(await api.post<Me>("/auth/totp/enable", { code })); setSetup(null); setToast("Двухфакторная аутентификация включена"); } catch (e: any) { setErr(e.message); }
            }}>
              <p className="wide">1. Отсканируйте код в приложении-аутентификаторе.</p>
              <img className="qr wide" src={`/api/auth/totp/qr.svg?t=${setup.secret.slice(0, 4)}`} alt="QR-код для приложения-аутентификатора" />
              <p className="wide small muted">Или введите ключ вручную: <span className="mono">{setup.secret}</span></p>
              <label className="field wide"><span>2. Введите 6-значный код из приложения</span><input inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} /></label>
              <p className="wide small muted">Сохраните ключ в надёжном месте офлайн: он понадобится, если телефон потеряется.</p>
              <div className="form-actions wide"><button className="btn primary">Подтвердить</button></div>
            </form>
          )}
        </section>
      </div>
      <ErrorLine error={err} />
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
