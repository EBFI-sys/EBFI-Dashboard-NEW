import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Moon, Sun, BookOpen, CalendarRange, FileText, Gauge, History, Inbox, Landmark, LineChart, UserCog, Wallet } from "lucide-react";
import { AuthProvider, useAuth } from "./auth";
import { CurrencyProvider } from "./currency";
import "./styles.css";
import Audit from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
import JobCard from "./pages/JobCard";
import Jobs from "./pages/Jobs";
import Login from "./pages/Login";
import Payouts from "./pages/Payouts";
import Pnl from "./pages/Pnl";
import Profile from "./pages/Profile";
import References from "./pages/References";
import Requests from "./pages/Requests";
import Sales from "./pages/Sales";
import Tds from "./pages/Tds";
import Users from "./pages/Users";

const NAV = [
  { group: "Работа", items: [
    { to: "/", label: "Дашборд", end: true, icon: Gauge },
    { to: "/requests", label: "Заявки", icon: Inbox },
    { to: "/jobs", label: "Табель", icon: CalendarRange },
  ] },
  { group: "Финансы", items: [
    { to: "/pnl", label: "P&L по месяцам", icon: LineChart },
    { to: "/sales", label: "Инвойсы клиентам", icon: FileText },
    { to: "/payouts", label: "Счета инспекторов", icon: Wallet },
    { to: "/tds", label: "Реестр TDS", icon: Landmark },
  ] },
  { group: "Система", items: [
    { to: "/references", label: "Справочники", icon: BookOpen },
    { to: "/audit", label: "Журнал изменений", icon: History },
  ] },
];

function ThemeSwitch() {
  const [theme, setTheme] = React.useState(() => document.documentElement.dataset.theme || "dark");
  const set = (t: string) => {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("ebfi.theme", t); } catch { /* private window */ }
  };
  return (
    <div className="theme-switch" role="group" aria-label="Тема оформления">
      <button type="button" className={theme === "dark" ? "on" : ""} onClick={() => set("dark")}><Moon aria-hidden />Ночь</button>
      <button type="button" className={theme === "light" ? "on" : ""} onClick={() => set("light")}><Sun aria-hidden />День</button>
    </div>
  );
}

function Shell() {
  const { me, loading, logout, can } = useAuth();
  if (loading) return <div className="center muted">Загрузка…</div>;
  if (!me) return <Login />;
  const needs2fa = me.totp_required && !me.totp_enabled;
  return (
    <div className="shell">
      <aside className="side">
        <div className="side-brand">
          <span className="brand-mark small">EBFI</span>
          <span>Ops<small>Engineering Bureau International</small></span>
        </div>
        <nav>
          {NAV.map((g) => (
            <div key={g.group} style={{ display: "contents" }}>
              <div className="nav-group">{g.group}</div>
              {g.items.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}><n.icon aria-hidden />{n.label}</NavLink>
              ))}
              {g.group === "Система" && can("users") && <NavLink to="/users"><UserCog aria-hidden />Пользователи</NavLink>}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <ThemeSwitch />
          <NavLink to="/profile" className="me">
            <span className="avatar">{me.initials}</span>
            <span>{me.name}<small>{{ admin: "админ", accountant: "бухгалтер", manager: "менеджер" }[me.role]}</small></span>
          </NavLink>
          <button className="btn ghost small" onClick={logout}>Выйти</button>
        </div>
      </aside>
      <main className="main">
        {needs2fa && (
          <div className="banner">
            Для вашей роли нужна двухфакторная аутентификация. Пока она не включена, изменения сохранить нельзя.{" "}
            <NavLink to="/profile">Включить в профиле</NavLink>
          </div>
        )}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/requests" element={<Requests />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobCard />} />
          <Route path="/pnl" element={<Pnl />} />
          <Route path="/sales" element={<Sales />} />
          <Route path="/payouts" element={<Payouts />} />
          <Route path="/tds" element={<Tds />} />
          <Route path="/references" element={<References />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/users" element={<Users />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <CurrencyProvider>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </CurrencyProvider>
    </AuthProvider>
  </React.StrictMode>,
);
