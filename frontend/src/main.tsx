import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ActiveCtx, PageCtx, TrayBar, TrayCtx, TrayProvider } from "./components/ui";
import { Clock, ListChecks, Menu, Moon, RefreshCw, Sun, X, BookOpen, CalendarRange, FileText, Gauge, History, Inbox, Landmark, LineChart, UserCog, Wallet } from "lucide-react";
import { AuthProvider, useAuth } from "./auth";
import { CurrencyProvider } from "./currency";
import "./styles.css";
import Audit from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
import JobCard from "./pages/JobCard";
import Jobs from "./pages/Jobs";
import Login from "./pages/Login";
import MyDay from "./pages/MyDay";
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
    { to: "/my", label: "Мой день", icon: ListChecks },
    { to: "/", label: "Дашборд", end: true, icon: Gauge },
    { to: "/requests", label: "Заявки", icon: Inbox },
    { to: "/jobs", label: "Табель", icon: CalendarRange },
  ] },
  { group: "Финансы", items: [
    { to: "/pnl", label: "Финансовые результаты", icon: LineChart },
    { to: "/sales", label: "Реестр исходящих счетов", icon: FileText },
    { to: "/payouts", label: "Реестр входящих счетов", icon: Wallet },
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

/** Running India date and time: the app treats it as «now» (requests month, dates, month of new records). */
function IstClock() {
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const tz = "Asia/Kolkata";
  const date = new Intl.DateTimeFormat("ru-RU", { timeZone: tz, weekday: "short", day: "numeric", month: "long", year: "numeric" }).format(now)
    .replace(/\s?г\.$/, "").replace(/^./, (c) => c.toUpperCase());
  const time = new Intl.DateTimeFormat("ru-RU", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(now);
  return (
    <div className="ist-clock" title="Время в Индии (IST, UTC+5:30) — по нему система определяет текущую дату">
      <Clock aria-hidden />
      <span className="ist-date">{date}</span>
      <span className="ist-time">{time}</span>
      <span className="ist-zone">IST</span>
    </div>
  );
}

const PAGES: [string, React.ReactNode][] = [
  ["/", <Dashboard />], ["/my", <MyDay />], ["/requests", <Requests />], ["/jobs", <Jobs />], ["/jobs/:id", <JobCard />], ["/pnl", <Pnl />],
  ["/sales", <Sales />], ["/payouts", <Payouts />], ["/tds", <Tds />], ["/references", <References />], ["/audit", <Audit />],
  ["/users", <Users />], ["/profile", <Profile />],
];
const LABEL: Record<string, string> = {
  "/": "Дашборд", "/my": "Мой день", "/requests": "Заявки", "/jobs": "Табель", "/pnl": "Финансовые результаты", "/sales": "Исходящие счета", "/payouts": "Входящие счета",
  "/tds": "Реестр TDS", "/references": "Справочники", "/audit": "Журнал", "/users": "Пользователи", "/profile": "Профиль",
};

function NotFound() {
  const active = React.useContext(ActiveCtx);
  return active ? <Navigate to="/" /> : null;
}

/** Pages stay alive in the background after you leave them (the last 10, and any with a folded dialog), so a half-filled
 *  form in the tray is still there when you come back. A page refreshes its data each time it comes on screen again. */
function KeepAlive() {
  const loc = useLocation();
  const nav = useNavigate();
  const { items } = React.useContext(TrayCtx);
  const cur = loc.pathname;
  const [order, setOrder] = React.useState<string[]>([cur]);
  React.useEffect(() => {
    setOrder((o) => {
      const pinned = new Set(items.map((t) => t.path));
      const next = [cur, ...o.filter((p) => p !== cur)];
      return next.filter((p, i) => i < 10 || pinned.has(p));
    });
  }, [cur, items]);
  // every page keeps its own scroll position: back from a job card lands where the job was in the list
  const scrolls = React.useRef<Record<string, number>>({});
  const curRef = React.useRef(cur);
  React.useEffect(() => {
    try { window.history.scrollRestoration = "manual"; } catch { /* old browsers */ }
    const onScroll = () => { scrolls.current[curRef.current] = window.scrollY; };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  React.useLayoutEffect(() => {
    curRef.current = cur;
    const y = scrolls.current[cur] ?? 0;
    window.scrollTo(0, y);
    const t = setTimeout(() => window.scrollTo(0, scrolls.current[cur] ?? y), 60); // after the page has drawn
    return () => clearTimeout(t);
  }, [cur]);
  const paths = order.includes(cur) ? order : [cur, ...order];
  // stable render order, so React keeps every page's state while the visit order changes
  const sorted = [...paths].sort();
  return (
    <>
      {sorted.map((p) => (
        <div key={p} hidden={p !== cur} className="page-slot">
          <ActiveCtx.Provider value={p === cur}>
            <PageCtx.Provider value={{ path: p, label: LABEL[p] ?? (p.startsWith("/jobs/") ? "Карточка работы" : "") }}>
              <Routes location={p}>
                {PAGES.map(([path, el]) => <Route key={path} path={path} element={el} />)}
                <Route path="*" element={<NotFound />} />
              </Routes>
            </PageCtx.Provider>
          </ActiveCtx.Provider>
        </div>
      ))}
      <TrayBar go={(p) => p !== cur && nav(p)} />
    </>
  );
}

/** Phone: the three working sections as a tab bar at the bottom, everything else under «Ещё». */
/** Phone: pull the page down at the top to reload it. */
function PullToRefresh() {
  const [pull, setPull] = React.useState(0);
  const [spin, setSpin] = React.useState(false);
  React.useEffect(() => {
    if (!window.matchMedia("(max-width: 820px)").matches) return;
    let y0: number | null = null;
    let d = 0;
    const start = (e: TouchEvent) => {
      y0 = window.scrollY <= 0 && document.body.style.overflow !== "hidden" && !document.querySelector(".msheet-back") ? e.touches[0].clientY : null;
      d = 0;
    };
    const move = (e: TouchEvent) => {
      if (y0 == null) return;
      d = e.touches[0].clientY - y0;
      if (d > 0 && window.scrollY <= 0) setPull(Math.min(d, 120));
      else { y0 = null; setPull(0); }
    };
    const end = () => {
      if (y0 != null && d > 75) {
        setSpin(true);
        window.dispatchEvent(new Event("ebfi:refresh"));
        setTimeout(() => setSpin(false), 900);
      }
      y0 = null;
      setPull(0);
    };
    window.addEventListener("touchstart", start, { passive: true });
    window.addEventListener("touchmove", move, { passive: true });
    window.addEventListener("touchend", end);
    return () => {
      window.removeEventListener("touchstart", start);
      window.removeEventListener("touchmove", move);
      window.removeEventListener("touchend", end);
    };
  }, []);
  if (!pull && !spin) return null;
  return (
    <div className={"ptr" + (spin ? " spin" : "")} style={{ opacity: spin ? 1 : Math.min(1, pull / 75), transform: `translateY(${spin ? 30 : pull / 2}px) rotate(${pull * 3}deg)` }}>
      <RefreshCw aria-hidden />
    </div>
  );
}

function MobileNav() {
  const { me, logout, can } = useAuth();
  const [open, setOpen] = React.useState(false);
  const loc = useLocation();
  React.useEffect(() => setOpen(false), [loc.pathname]);
  const main = NAV[0].items.filter((n) => n.to !== "/");  // Мой день, Заявки, Табель; Дашборд is under «Ещё»
  const onMain = main.some((n) => (n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to)));
  return (
    <>
      <nav className="mtabs" aria-label="Разделы">
        {main.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}><n.icon aria-hidden /><span>{n.label}</span></NavLink>
        ))}
        <button type="button" className={!onMain || open ? "active" : ""} onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? <X aria-hidden /> : <Menu aria-hidden />}<span>Ещё</span>
        </button>
      </nav>
      {open && (
        <div className="msheet-back" onClick={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className="msheet" role="dialog" aria-label="Все разделы">
            {NAV.map((g) => ({ ...g, items: g.items.filter((n) => !main.includes(n)) })).filter((g) => g.items.length).map((g) => (
              <div key={g.group}>
                <div className="nav-group">{g.group}</div>
                {g.items.map((n) => <NavLink key={n.to} to={n.to} end={n.end}><n.icon aria-hidden />{n.label}</NavLink>)}
                {g.group === "Система" && can("users") && <NavLink to="/users"><UserCog aria-hidden />Пользователи</NavLink>}
              </div>
            ))}
            <div className="msheet-foot">
              <ThemeSwitch />
              <NavLink to="/profile" className="me">
                <span className="avatar">{me?.initials}</span>
                <span>{me?.name}<small>{{ admin: "админ", accountant: "бухгалтер", manager: "менеджер" }[me?.role ?? "manager"]}</small></span>
              </NavLink>
              <button className="btn ghost small" onClick={logout}>Выйти</button>
            </div>
          </div>
        </div>
      )}
    </>
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
        <div className="topbar"><IstClock /></div>
        {needs2fa && (
          <div className="banner">
            Для вашей роли нужна двухфакторная аутентификация. Пока она не включена, изменения сохранить нельзя.{" "}
            <NavLink to="/profile">Включить в профиле</NavLink>
          </div>
        )}
        <KeepAlive />
      </main>
      <MobileNav />
      <PullToRefresh />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <CurrencyProvider>
        <TrayProvider>
          <BrowserRouter>
            <Shell />
          </BrowserRouter>
        </TrayProvider>
      </CurrencyProvider>
    </AuthProvider>
  </React.StrictMode>,
);
