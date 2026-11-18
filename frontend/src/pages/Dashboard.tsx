import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money, monthLabel, num, pct } from "../api";
import { ErrorLine, Pill, useAsync } from "../components/ui";
import { REGIONS, useRef_ } from "../refs";

const TABS = [
  { id: "overview", label: "Обзор и финансы" },
  { id: "ops", label: "Заявки и операции" },
  { id: "cash", label: "Счета и cash flow" },
  { id: "insp", label: "Инспекторы" },
];

function monthsBack(n: number) {
  const out: string[] = [];
  const d = new Date();
  for (let i = 0; i < n; i++) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}

const C1 = "#3d6fb6", C2 = "#c47a2c", GRID = "var(--line)";

export default function Dashboard() {
  const clients = useRef_("clients");
  const users = useRef_("users");
  const [f, setF] = useState({ period: "all", client_id: "", region: "", owner_id: "", currency: "INR" });
  const [tab, setTab] = useState(() => (location.hash.slice(1) || "overview"));
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== "") as [string, string][]).toString();
  const { data: d, error, loading } = useAsync(() => api.get(`/dashboard?${qs}`), [qs]);
  const cur = f.currency;
  const m = (v: number | null | undefined) => money(v, cur, true);
  const months = useMemo(() => monthsBack(18), []);
  const go = (t: string) => {
    setTab(t);
    history.replaceState(null, "", "#" + t);
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Дашборд</h1>
          {d && (
            <p className="lede">
              За выбранный период выручка <b>{m(d.kpi.revenue)}</b>, чистая прибыль <b>{m(d.kpi.net)}</b> (маржа <b>{pct(d.kpi.margin)}</b>),{" "}
              <b>{num(d.kpi.md, 1)}</b> человеко-дней. Выручка считается без GST, TDS не уменьшает прибыль.
            </p>
          )}
        </div>
      </header>

      <div className="filters card">
        <label>Период
          <select value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })}>
            <option value="all">Все месяцы</option>
            <option value="fy">Текущий финансовый год (с апреля)</option>
            <option value="last3">Последние 3 месяца</option>
            {months.map((x) => <option key={x} value={x}>{monthLabel(x)}</option>)}
          </select>
        </label>
        <label>Клиент
          <select value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })}>
            <option value="">Все клиенты</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>Страна / регион
          <select value={f.region} onChange={(e) => setF({ ...f, region: e.target.value })}>
            <option value="">Все регионы</option>
            {REGIONS.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label>Координатор
          <select value={f.owner_id} onChange={(e) => setF({ ...f, owner_id: e.target.value })}>
            <option value="">Все</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.initials} · {u.name}</option>)}
          </select>
        </label>
        <div className="seg" role="group" aria-label="Валюта">
          {["INR", "USD", "EUR"].map((c) => (
            <button key={c} className={cur === c ? "on" : ""} onClick={() => setF({ ...f, currency: c })}>{c}</button>
          ))}
        </div>
      </div>

      {d?.provisional_months?.length > 0 && (
        <div className="banner soft">Курс не зафиксирован за: {d.provisional_months.map(monthLabel).join(", ")} — цифры предварительные (по курсу прошлого месяца).</div>
      )}
      <ErrorLine error={error} />

      <nav className="tabs" role="tablist">
        {TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => go(t.id)}>{t.label}</button>)}
      </nav>
      {loading && !d && <p className="muted">Загрузка…</p>}

      {d && tab === "overview" && (
        <>
          <div className="kpis">
            <Kpi label="Выручка (без GST)" value={m(d.kpi.revenue)} sub={`Приход на счёт: ${m(d.kpi.cash_in)}`} />
            <Kpi label="Чистая прибыль" value={m(d.kpi.net)} sub="После админки, подряда и РКО" tone={d.kpi.net < 0 ? "bad" : undefined} />
            <Kpi label="Маржа" value={pct(d.kpi.margin)} sub="Прибыль ÷ выручка" />
            <Kpi label="Человеко-дни" value={num(d.kpi.md, 1)} sub={`${d.kpi.jobs} работ`} />
            <Kpi label="Заказов в работе" value={String(d.kpi.active_jobs)} sub="«В работе» и «Пауза»" />
          </div>
          <section className="card">
            <h2>Выручка и прибыль по месяцам</h2>
            <div className="chart">
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={d.monthly.map((x: any) => ({ ...x, label: monthLabel(x.month) }))}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={(v) => m(v)} width={80} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v: number) => m(v)} />
                  <Legend />
                  <Bar dataKey="revenue" name="Выручка" fill={C1} radius={[3, 3, 0, 0]} />
                  <Line dataKey="net" name="Чистая прибыль" stroke={C2} strokeWidth={2.5} dot />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </section>
          <section className="card">
            <h2>Топ-10 клиентов</h2>
            <div className="chart">
              <ResponsiveContainer width="100%" height={Math.max(220, d.top_clients.length * 42)}>
                <BarChart data={d.top_clients} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid stroke={GRID} horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => m(v)} tick={{ fontSize: 12 }} />
                  <YAxis type="category" dataKey="client" width={150} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v: number) => m(v)} />
                  <Legend />
                  <Bar dataKey="revenue" name="Выручка" fill={C1} />
                  <Bar dataKey="net" name="Чистая прибыль" fill={C2} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}

      {d && tab === "ops" && (
        <>
          <div className="kpis">
            <Kpi label="Заявок" value={String(d.requests.total)} />
            <Kpi label="Конверсия в выполнение" value={pct(d.requests.conversion)} sub="Выполнено ÷ все" />
            <Kpi label="Выигрыш среди закрытых" value={pct(d.requests.win_rate)} sub="Выполнено ÷ (выполнено + отмена)" />
          </div>
          <div className="grid2">
            <section className="card">
              <h2>Заявки по статусам</h2>
              <table><tbody>
                {Object.entries(d.requests.by_status).sort((a: any, b: any) => b[1] - a[1]).map(([s, n]: any) => (
                  <tr key={s}><td><Pill status={s} /></td><td className="r">{n}</td>
                    <td className="bar-cell"><span style={{ width: `${(n / Math.max(1, d.requests.total)) * 100}%` }} /></td></tr>
                ))}
              </tbody></table>
            </section>
            <section className="card">
              <h2>Где инспекции</h2>
              <Table rows={d.regions} cols={[
                { k: "region", l: "Регион" }, { k: "jobs", l: "Работ", r: true }, { k: "md", l: "MD", r: true, f: (v) => num(v, 1) },
                { k: "revenue", l: "Выручка", r: true, f: m }, { k: "margin", l: "Маржа", r: true, f: pct },
              ]} />
            </section>
          </div>
          <section className="card">
            <h2>По координаторам</h2>
            <Table rows={d.owners} cols={[
              { k: "owner", l: "Чья" }, { k: "jobs", l: "Работ", r: true }, { k: "md", l: "MD", r: true, f: (v) => num(v, 1) },
              { k: "revenue", l: "Выручка", r: true, f: m }, { k: "net", l: "Чистая прибыль", r: true, f: m }, { k: "margin", l: "Маржа", r: true, f: pct },
            ]} />
          </section>
          <section className="card">
            <h2>Активные заказы</h2>
            <Table rows={d.active} cols={[
              { k: "status", l: "Статус", f: (v) => <Pill status={v} /> }, { k: "job_number", l: "Job №", f: (v, r) => <Link to={`/jobs/${r.job_id}`}>{v}</Link> },
              { k: "client", l: "Клиент" }, { k: "country", l: "Страна" }, { k: "inspector", l: "Инспектор" }, { k: "owner", l: "Чья" },
              { k: "month", l: "Месяц", f: monthLabel }, { k: "md", l: "MD", r: true }, { k: "revenue", l: "Выручка", r: true, f: m }, { k: "net", l: "Прибыль", r: true, f: m },
            ]} />
          </section>
        </>
      )}

      {d && tab === "cash" && (
        <div className="grid2">
          <section className="card">
            <h2>Инвойсы клиентам</h2>
            <p className="muted">Применяется только фильтр по клиенту.</p>
            <Table rows={d.sales_by_currency} cols={[
              { k: "currency", l: "Валюта" }, { k: "count", l: "Инвойсов", r: true },
              { k: "invoiced", l: "Выставлено", r: true, f: (v, r) => money(v, r.currency) },
              { k: "received", l: "Получено", r: true, f: (v, r) => money(v, r.currency) },
              { k: "outstanding", l: "К получению", r: true, f: (v, r) => <b className={v > 0 ? "neg" : ""}>{money(v, r.currency)}</b> },
            ]} />
            <h3>Реестр TDS</h3>
            <p>Ожидается к зачёту: <b>{money(d.tds.expected)}</b> · зачтено: <b>{money(d.tds.credited)}</b> · <Link to="/tds">открыть реестр</Link></p>
            <p><Link to="/sales">Все инвойсы клиентам →</Link></p>
          </section>
          <section className="card">
            <h2>Выплаты инспекторам</h2>
            <Table rows={d.payables_by_currency} cols={[
              { k: "currency", l: "Валюта" },
              { k: "paid", l: "Оплачено", r: true, f: (v, r) => money(v, r.currency) },
              { k: "to_pay", l: "К оплате", r: true, f: (v, r) => <b className={v > 0 ? "neg" : ""}>{money(v, r.currency)}</b> },
              { k: "open", l: "Счетов к оплате", r: true },
            ]} />
            <p><Link to="/payouts">Все счета инспекторов →</Link></p>
          </section>
        </div>
      )}

      {d && tab === "insp" && <Inspectors d={d} m={m} />}
    </div>
  );
}

function Inspectors({ d, m }: { d: any; m: (v: number) => string }) {
  const [q, setQ] = useState("");
  const rows = d.inspectors.filter((r: any) => r.inspector.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <section className="card">
        <div className="toolbar">
          <h2>Рейтинг инспекторов</h2>
          <div className="spacer" />
          <input className="search" placeholder="Найти инспектора" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Table rows={rows} cols={[
          { k: "inspector", l: "Инспектор" }, { k: "md", l: "MD", r: true, f: (v) => num(v, 1) }, { k: "jobs", l: "Работ", r: true },
          { k: "revenue", l: "Выручка", r: true, f: m }, { k: "net", l: "Прибыль", r: true, f: (v) => <span className={v < 0 ? "neg" : ""}>{m(v)}</span> },
          { k: "margin", l: "Маржа", r: true, f: pct }, { k: "net_per_md", l: "Прибыль / MD", r: true, f: m },
          { k: "loss_lines", l: "Убыточных строк", r: true, f: (v) => (v ? <span className="pill bad">{v}</span> : "0") },
        ]} />
      </section>
      <section className="card">
        <h2>Убыточные строки</h2>
        <Table rows={d.loss_lines} cols={[
          { k: "month", l: "Месяц", f: monthLabel }, { k: "job_number", l: "Job №", f: (v, r) => <Link to={`/jobs/${r.job_id}`}>{v}</Link> },
          { k: "client", l: "Клиент" }, { k: "inspector", l: "Инспектор" }, { k: "country", l: "Страна" },
          { k: "revenue", l: "Выручка", r: true, f: m }, { k: "net", l: "Прибыль", r: true, f: (v) => <span className="neg">{m(v)}</span> },
        ]} empty="Убыточных строк нет." />
      </section>
    </>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="kpi card">
      <span className="kpi-label">{label}</span>
      <span className={"kpi-value " + (tone ?? "")}>{value}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}

type Col = { k: string; l: string; r?: boolean; f?: (v: any, row: any) => React.ReactNode };
export function Table({ rows, cols, empty = "Нет данных для этих фильтров." }: { rows: any[]; cols: Col[]; empty?: string }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c.k} className={c.r ? "r" : ""}>{c.l}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{cols.map((c) => <td key={c.k} className={c.r ? "r" : ""}>{c.f ? c.f(row[c.k], row) : row[c.k] ?? "—"}</td>)}</tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={cols.length} className="empty">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
