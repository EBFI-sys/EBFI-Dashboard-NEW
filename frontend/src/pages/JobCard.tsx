import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, dateLabel, inr, money, monthLabel, num, pct, thisMonth } from "../api";
import { useAuth } from "../auth";
import { EditForm, Field } from "../components/CrudTable";
import { ErrorLine, Pill, Toast, useAsync } from "../components/ui";
import { CURRENCIES } from "../refs";
import { jobFields } from "./Jobs";

export const lineFields: Field[] = [
  { key: "month", label: "Месяц (ГГГГ-ММ)", required: true },
  { key: "inspector_id", label: "Инспектор", type: "ref", ref: "inspectors" },
  { key: "dates_text", label: "Даты работ", wide: true },
  { key: "quantity", label: "Количество (MD, часы, тонны)", type: "number", required: true },
  { key: "unit", label: "Единица", type: "select", options: ["day", "hour", "ton", "lump"], required: true },
  { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, required: true },
  { key: "client_rate", label: "Ставка клиенту", type: "money", required: true },
  { key: "inspector_rate", label: "Ставка инспектору", type: "money" },
  { key: "overtime_client", label: "Overtime клиенту (сумма)", type: "money" },
  { key: "overtime_inspector", label: "Overtime инспектору (сумма)", type: "money" },
  { key: "no_subcontractor", label: "Без подрядчика", type: "bool" },
  { key: "payment_method_id", label: "Способ оплаты инспектору (для РКО)", type: "ref", ref: "payment-methods" },
  { key: "rko_override_inr", label: "РКО вручную, ₹", type: "money", hint: "Оставьте пустым — посчитается по способу оплаты" },
  { key: "notes", label: "Примечания", type: "textarea" },
];

export default function JobCard() {
  const { id } = useParams();
  const { can } = useAuth();
  const { data: j, error, reload } = useAsync(() => api.get(`/jobs/${id}`), [id]);
  const [editJob, setEditJob] = useState(false);
  const [line, setLine] = useState<any | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const hist = useAsync(() => api.get(`/audit?table=jobs&record_id=${id}`), [id, j]);

  if (error) return <div className="page"><ErrorLine error={error} /></div>;
  if (!j) return <div className="page muted">Загрузка…</div>;

  const saveLine = async (d: any) => {
    if (d.id) await api.patch(`/lines/${d.id}`, d);
    else await api.post("/lines", { ...d, job_id: j.id });
    setLine(null);
    setToast("Строка сохранена");
    reload();
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs"><Link to="/jobs">Работы</Link> /</p>
          <h1 className="mono">{j.job_number} <Pill status={j.status} /></h1>
          <p className="lede">{j.client_name} · {j.country ?? "—"} · {j.vendor ?? "завод не указан"} · Чья: {j.owner ?? "—"}</p>
        </div>
        {can("write") && <button className="btn" onClick={() => setEditJob(true)}>Изменить работу</button>}
      </header>

      <div className="kpis">
        <div className="kpi card"><span className="kpi-label">Выручка</span><span className="kpi-value">{inr(j.totals.base_inr)}</span></div>
        <div className="kpi card"><span className="kpi-label">Чистая прибыль</span><span className={"kpi-value " + (j.totals.net_inr < 0 ? "bad" : "")}>{inr(j.totals.net_inr)}</span></div>
        <div className="kpi card"><span className="kpi-label">Человеко-дни</span><span className="kpi-value">{num(j.totals.man_days, 1)}</span></div>
      </div>

      <section className="card">
        <div className="toolbar">
          <h2>Строки по месяцам</h2>
          <div className="spacer" />
          {can("write") && (
            <button className="btn primary" onClick={() => setLine({ month: thisMonth(), unit: "day", currency: j.lines.at(-1)?.currency ?? "USD", quantity: 1,
              client_rate: j.lines.at(-1)?.client_rate, inspector_rate: j.lines.at(-1)?.inspector_rate, inspector_id: j.lines.at(-1)?.inspector_id })}>Добавить строку</button>
          )}
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>Месяц</th><th>Инспектор</th><th>Даты</th><th className="r">Кол-во</th><th className="r">Ставка клиенту</th><th className="r">Ставка инсп.</th>
              <th className="r">Курс</th><th className="r">Выручка ₹</th><th className="r">GST</th><th className="r">TDS</th><th className="r">Админка</th>
              <th className="r">Подряд</th><th className="r">РКО</th><th className="r">Прибыль ₹</th><th className="r">Маржа</th><th />
            </tr></thead>
            <tbody>
              {j.lines.map((l: any) => (
                <tr key={l.id}>
                  <td>{monthLabel(l.month)}{l.calc.closed && <span className="pill mute">закрыт</span>}</td>
                  <td>{l.inspector_name ?? (l.no_subcontractor ? "без подрядчика" : "—")}</td>
                  <td className="wrap">{l.dates_text ?? "—"}</td>
                  <td className="r">{num(l.quantity, 2).replace(/\.00$/, "")} {l.unit !== "day" && l.unit}</td>
                  <td className="r">{money(l.client_rate, l.currency)}</td>
                  <td className="r">{l.no_subcontractor ? "—" : money(l.inspector_rate, l.currency)}</td>
                  <td className="r" title={l.calc.fx_provisional ? `Предварительный курс из ${l.calc.fx_source_month}` : ""}>
                    {l.currency === "INR" ? "—" : num(l.calc.fx, 2)}{l.calc.fx_provisional && l.currency !== "INR" && " *"}
                  </td>
                  <td className="r">{inr(l.calc.base_inr)}</td><td className="r">{inr(l.calc.gst_inr)}</td><td className="r">{inr(l.calc.tds_inr)}</td>
                  <td className="r">{inr(l.calc.admin_inr)}</td><td className="r">{inr(l.calc.cost_inr)}</td><td className="r">{inr(l.calc.rko_inr)}</td>
                  <td className={"r " + ((l.calc.net_inr ?? 0) < 0 ? "neg" : "")}><b>{inr(l.calc.net_inr)}</b></td>
                  <td className="r">{pct(l.calc.margin)}</td>
                  <td className="actions">{can("write") && !l.calc.closed && <button className="btn small ghost" onClick={() => setLine(l)}>Изменить</button>}</td>
                </tr>
              ))}
              {j.lines.length === 0 && <tr><td colSpan={16} className="empty">Строк ещё нет. Добавьте первый месяц работы.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="muted small">* курс не зафиксирован — используется курс прошлого месяца. GST и TDS считаются только для клиентов из Индии.</p>
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Инвойсы клиенту</h2>
          {j.sales_invoices.length === 0 ? <p className="muted">Нет. Создайте инвойс на странице «Инвойсы клиентам» из строк этой работы.</p> : (
            <table><tbody>{j.sales_invoices.map((s: any) => (
              <tr key={s.id}><td className="mono">{s.number}</td><td>{dateLabel(s.date)}</td><td className="r">{money(s.amount, s.currency)}</td><td><Pill status={s.status} /></td></tr>
            ))}</tbody></table>
          )}
        </section>
        <section className="card">
          <h2>Счета инспекторов</h2>
          {j.inspector_invoices.length === 0 ? <p className="muted">Нет привязанных счетов.</p> : (
            <table><tbody>{j.inspector_invoices.map((s: any) => (
              <tr key={s.id}><td>{s.number ?? "—"}</td><td>{dateLabel(s.invoice_date)}</td><td className="r">{money(s.amount, s.currency)}</td><td><Pill status={s.paid ? "Оплачено" : "К оплате"} /></td></tr>
            ))}</tbody></table>
          )}
        </section>
      </div>

      <section className="card">
        <h2>История изменений работы</h2>
        <table><tbody>
          {(hist.data ?? []).slice(0, 30).map((a: any) => (
            <tr key={a.id}><td className="nowrap">{new Date(a.at).toLocaleString("ru-RU")}</td><td>{a.user ?? "система"}</td><td>{a.action}</td>
              <td className="wrap small">{Object.entries(a.changes).map(([k, v]: any) => `${k}: ${Array.isArray(v) ? `${v[0] ?? "—"} → ${v[1] ?? "—"}` : v}`).join("; ")}</td></tr>
          ))}
        </tbody></table>
      </section>

      {editJob && <EditForm title="Изменить работу" fields={jobFields} initial={j} onCancel={() => setEditJob(false)}
        onSave={async (d) => { await api.patch(`/jobs/${j.id}`, d); setEditJob(false); setToast("Сохранено"); reload(); }} />}
      {line && <EditForm title={line.id ? "Изменить строку" : "Новая строка"} fields={lineFields} initial={line} onCancel={() => setLine(null)} onSave={saveLine} />}
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
