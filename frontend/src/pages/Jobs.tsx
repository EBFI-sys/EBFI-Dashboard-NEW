import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, downloadCsv, inr, num } from "../api";
import { useAuth } from "../auth";
import { EditForm, Field } from "../components/CrudTable";
import { JobsCalendar } from "../components/Calendar";
import { ErrorLine, Pill, useAsync } from "../components/ui";
import { JOB_STATUSES } from "../refs";

export const jobFields: Field[] = [
  { key: "job_number", label: "Job number", required: true, hint: "Формат ГГ.КК-ННН, например 26.19-478" },
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "client_contact", label: "Контакт клиента" },
  { key: "client_job_number", label: "Client Job Number" },
  { key: "vendor", label: "Завод (vendor)", wide: true },
  { key: "country", label: "Страна" },
  { key: "owner_id", label: "Чья", type: "ref", ref: "users", refLabel: "initials" },
  { key: "status", label: "Статус", type: "select", options: JOB_STATUSES, required: true },
  { key: "notes", label: "Примечания", type: "textarea" },
];

export default function Jobs() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [status, setStatus] = useState("В работе,Пауза");
  const [q, setQ] = useState("");
  const [add, setAdd] = useState(false);
  const [cal, setCal] = useState(false);
  const { data, error, loading } = useAsync(() => api.get<any[]>(`/jobs?status=${encodeURIComponent(status)}`), [status]);
  const rows = (data ?? []).filter((j) => !q || `${j.job_number} ${j.client_name} ${j.vendor} ${j.country}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="page">
      <header className="page-head"><h1>Работы</h1><button className="btn" onClick={() => setCal(true)}>Календарь дат</button></header>
      <section className="card">
        <div className="toolbar">
          <div className="seg">
            {[["В работе,Пауза", "Активные"], ["Сдан", "Сданные"], ["", "Все"]].map(([v, l]) => (
              <button key={l} className={status === v ? "on" : ""} onClick={() => setStatus(v)}>{l}</button>
            ))}
          </div>
          <span className="muted">{loading ? "Загрузка…" : `${rows.length} работ`}</span>
          <div className="spacer" />
          <input className="search" placeholder="Job №, клиент, завод" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn ghost" onClick={() => downloadCsv("jobs.csv", rows.map((r) => ({ ...r, base: r.totals.base_inr, net: r.totals.net_inr, md: r.totals.man_days })),
            [{ key: "job_number", label: "Job" }, { key: "client_name", label: "Клиент" }, { key: "country", label: "Страна" }, { key: "owner", label: "Чья" },
             { key: "status", label: "Статус" }, { key: "md", label: "MD" }, { key: "base", label: "Выручка INR" }, { key: "net", label: "Прибыль INR" }])}>CSV</button>
          {can("write") && <button className="btn primary" onClick={() => setAdd(true)}>Новая работа</button>}
        </div>
        <ErrorLine error={error} />
        <div className="table-wrap">
          <table>
            <thead><tr><th>Статус</th><th>Job №</th><th>Клиент</th><th>Завод</th><th>Страна</th><th>Чья</th><th>Месяцы</th><th className="r">MD</th><th className="r">Выручка</th><th className="r">Прибыль</th></tr></thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.id} className="clickable" onClick={() => nav(`/jobs/${j.id}`)}>
                  <td><Pill status={j.status} />{j.pre_november && <span className="pill mute" title="Открыта до запуска системы">до ноября</span>}</td>
                  <td className="mono">{j.job_number}</td><td>{j.client_name}</td><td className="wrap">{j.vendor ?? "—"}</td><td>{j.country ?? "—"}</td>
                  <td>{j.owner ?? "—"}</td><td>{j.months.join(", ")}</td>
                  <td className="r">{num(j.totals.man_days, 1)}</td><td className="r">{inr(j.totals.base_inr)}</td>
                  <td className={"r " + (j.totals.net_inr < 0 ? "neg" : "")}>{inr(j.totals.net_inr)}</td>
                </tr>
              ))}
              {!loading && rows.length === 0 && <tr><td colSpan={10} className="empty">Работ не найдено.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      {cal && <JobsCalendar onClose={() => setCal(false)} />}
      {add && (
        <EditForm title="Новая работа" fields={jobFields} initial={{ status: "В работе" }} onCancel={() => setAdd(false)}
          onSave={async (d) => { const j = await api.post("/jobs", d); nav(`/jobs/${j.id}`); }} />
      )}
    </div>
  );
}
