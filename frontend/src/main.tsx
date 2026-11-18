import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
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
  { to: "/", label: "Дашборд", end: true },
  { to: "/requests", label: "Заявки" },
  { to: "/jobs", label: "Работы" },
  { to: "/pnl", label: "P&L по месяцам" },
  { to: "/sales", label: "Инвойсы клиентам" },
  { to: "/payouts", label: "Счета инспекторов" },
  { to: "/tds", label: "Реестр TDS" },
  { to: "/references", label: "Справочники" },
  { to: "/audit", label: "Журнал изменений" },
];

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
          <span>Ops</span>
        </div>
        <nav>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>{n.label}</NavLink>
          ))}
          {can("users") && <NavLink to="/users">Пользователи</NavLink>}
        </nav>
        <div className="side-foot">
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
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
);
