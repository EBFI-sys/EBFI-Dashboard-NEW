import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, compactDates, downloadCsv, money, num } from "../api";
import { useAuth } from "../auth";
import { JobDatesModal, JobsCalendar } from "../components/Calendar";
import { EditForm, Field } from "../components/CrudTable";
import DataTable, { Col } from "../components/DataTable";
import { ErrorLine, Pill, useAsync } from "../components/ui";
import { CurrencySwitch, useCurrency } from "../currency";
import { JOB_STATUSES, useRef_ } from "../refs";

export const jobFields: Field[] = [
  { key: "job_number", label: "Job number", required: true, hint: "Формат ГГ.КК-ННН, например 26.19-478" },
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "client_contact", label: "Контакт клиента" },
  { key: "client_job_number", label: "Client Job Number" },
  { key: "vendor", label: "Завод (Vendor)", type: "suggest", ref: "vendors", wide: true, hint: "Начните вводить — система предложит заводы из справочника; новый завод добавится сам" },
  { key: "country", label: "Страна", type: "suggest", ref: "countries" },
  { key: "owner_id", label: "Чья", type: "ref", ref: "users", refLabel: "initials" },
  { key: "status", label: "Статус", type: "select", options: JOB_STATUSES, required: true },
  { key: "notes", label: "Примечания", type: "textarea" },
];

export default function Jobs() {
  const nav = useNavigate();
  const { can } = useAuth();
  const { cur, conv } = useCurrency();
  const inspectorRows = useRef_("inspectors");
  const inspectors = useMemo(() => new Map(inspectorRows.map((i) => [i.id, i])), [inspectorRows]);
  const [status, setStatus] = useState("В работе,Пауза");
  const [add, setAdd] = useState(false);
  const [cal, setCal] = useState(false);
  const [dates, setDates] = useState<any | null>(null);
  const [visible, setVisible] = useState<any[]>([]);
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(`/jobs?status=${encodeURIComponent(status)}`), [status]);

  // revenue and profit in the chosen currency: each month at its own rate
  const inCur = useCallback((j: any, k: "base_inr" | "net_inr") => {
    let sum = 0;
    for (const [m, t] of Object.entries<any>(j.totals_by_month ?? {})) {
      const v = conv(t[k], m);
      if (v == null) return null;
      sum += v;
    }
    return sum;
  }, [conv]);

  const rows = useMemo(() => (data ?? []).map((j) => ({
    ...j, revenue: inCur(j, "base_inr"), net: inCur(j, "net_inr"), md: j.totals.man_days, date_text: compactDates(j.dates ?? [], 99),
  })), [data, inCur]);

  const cols: Col[] = [
    { key: "status", label: "Статус", render: (j) => <><Pill status={j.status} /></> },
    { key: "job_number", label: "Job №", cls: "mono" },
    { key: "client_name", label: "Клиент" },
    { key: "vendor", label: "Завод", cls: "wrap" },
    { key: "country", label: "Страна" },
    { key: "owner", label: "Чья" },
    {
      key: "date_text", label: "Дата", text: (j) => compactDates(j.dates ?? [], 99) || null,
      render: (j) => (
        <button type="button" className={"date-cell" + (j.dates?.length ? "" : " empty-dates")} title="Открыть календарь дат инспекции"
          onClick={(e) => { e.stopPropagation(); setDates(j); }}>
          {j.dates?.length ? compactDates(j.dates) : "указать даты"}
        </button>
      ),
    },
    { key: "md", label: "MD", align: "r", render: (j) => num(j.md, 1) },
    { key: "revenue", label: `Выручка, ${cur}`, align: "r", render: (j) => money(j.revenue, cur) },
    { key: "net", label: `Прибыль, ${cur}`, align: "r", render: (j) => <span className={(j.net ?? 0) < 0 ? "neg" : ""}>{money(j.net, cur)}</span> },
  ];

  return (
    <div className="page">
      <header className="page-head">
        <h1>Табель</h1>
        <div className="head-actions">
          <CurrencySwitch />
          <button className="btn" onClick={() => setCal(true)}>Календарь дат</button>
        </div>
      </header>
      <section className="card">
        <div className="toolbar">
          <div className="seg">
            {[["В работе,Пауза", "Активные"], ["Сдан", "Сданные"], ["", "Все"]].map(([v, l]) => (
              <button key={l} className={status === v ? "on" : ""} onClick={() => setStatus(v)}>{l}</button>
            ))}
          </div>
          <span className="muted">{loading ? "Загрузка…" : `${visible.length} работ`}</span>
          <div className="spacer" />
          <button className="btn ghost" onClick={() => downloadCsv("tabel.csv", visible, [
            { key: "job_number", label: "Job" }, { key: "client_name", label: "Клиент" }, { key: "vendor", label: "Завод" }, { key: "country", label: "Страна" },
            { key: "owner", label: "Чья" }, { key: "status", label: "Статус" }, { key: "date_text", label: "Даты" }, { key: "md", label: "MD" },
            { key: "revenue", label: `Выручка ${cur}` }, { key: "net", label: `Прибыль ${cur}` }])}>CSV</button>
          {can("write") && <button className="btn primary" onClick={() => setAdd(true)}>Новая работа</button>}
        </div>
        <ErrorLine error={error} />
        <DataTable rows={rows} cols={cols} onRowClick={(j) => nav(`/jobs/${j.id}`)} onVisible={setVisible}
          empty={loading ? "Загрузка…" : "Работ не найдено."} />
      </section>
      {cal && <JobsCalendar onClose={() => setCal(false)} />}
      {dates && <JobDatesModal job={dates} inspectors={inspectors} onClose={() => setDates(null)} onSaved={reload} />}
      {add && (
        <EditForm title="Новая работа" fields={jobFields} initial={{ status: "В работе" }} onCancel={() => setAdd(false)}
          onSave={async (d) => { const j = await api.post("/jobs", d); nav(`/jobs/${j.id}`); }} />
      )}
    </div>
  );
}
