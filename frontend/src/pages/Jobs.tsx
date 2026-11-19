import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, compactDates, downloadCsv, num } from "../api";
import { useAuth } from "../auth";
import { JobDatesModal, JobsCalendar } from "../components/Calendar";
import { ClientChip, OwnerChip } from "../components/Chips";
import { EditForm, Field } from "../components/CrudTable";
import DataTable, { Col } from "../components/DataTable";
import { ErrorLine, Pill, useAsync } from "../components/ui";
import { CURRENCIES, JOB_STATUSES, loadRef, useRef_ } from "../refs";

export const jobFields: Field[] = [
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "job_number", label: "Job number", required: true, hint: "Подставляется по очереди номеров клиента; можно изменить" },
  { key: "client_contact", label: "Контакт клиента" },
  { key: "client_job_number", label: "Client Job Number" },
  { key: "vendor", label: "Завод (Vendor)", type: "suggest", ref: "vendors", wide: true, hint: "Начните вводить — система предложит заводы из справочника; новый завод добавится сам" },
  { key: "country", label: "Страна", type: "suggest", ref: "countries" },
  { key: "owner_id", label: "Чья", type: "ref", ref: "users", refLabel: "initials" },
  { key: "status", label: "Статус", type: "select", options: JOB_STATUSES, required: true },
  { key: "notes", label: "Примечания", type: "textarea" },
];

/** Inspector, dates and rates entered together with a new job (the first assignment). */
const firstAssignment: Field[] = [
  { key: "a_inspector_id", label: "Инспектор", type: "ref", ref: "inspectors" },
  { key: "a_dates_text", label: "Даты инспекции", type: "dates" },
  { key: "a_client_rate", label: "Ставка клиента (за день)", type: "money" },
  { key: "a_currency", label: "Валюта клиента", type: "select", options: CURRENCIES, required: true },
  { key: "a_inspector_rate", label: "Ставка инспектора (за день)", type: "money" },
  { key: "a_inspector_currency", label: "Валюта инспектора", type: "select", options: CURRENCIES, required: true },
];

/** "500 USD" for one rate, "500 / 450 USD" when the inspectors differ */
export function rateText(as: any[], rate: string, cur: string) {
  const vals = [...new Set(as.filter((a) => a[rate]).map((a) => `${num(a[rate], 2).replace(/\.00$/, "")}|${a[cur]}`))];
  if (!vals.length) return null;
  const curs = [...new Set(vals.map((v) => v.split("|")[1]))];
  return curs.length === 1 ? `${vals.map((v) => v.split("|")[0]).join(" / ")} ${curs[0]}` : vals.map((v) => v.replace("|", " ")).join(" / ");
}

function Rate({ text }: { text: string | null }) {
  if (!text) return <span className="muted">—</span>;
  const m = text.match(/^(.*) ([A-Z]{3})$/);
  return m ? <span className="rate">{m[1]}<small>{m[2]}</small></span> : <span className="rate">{text}</span>;
}

export default function Jobs() {
  const nav = useNavigate();
  const { can } = useAuth();
  const inspectorRows = useRef_("inspectors");
  const inspectors = useMemo(() => new Map(inspectorRows.map((i) => [i.id, i])), [inspectorRows]);
  const [status, setStatus] = useState("В работе,Пауза");
  const [add, setAdd] = useState(false);
  const [cal, setCal] = useState(false);
  const [dates, setDates] = useState<any | null>(null);
  const [visible, setVisible] = useState<any[]>([]);
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(`/jobs?status=${encodeURIComponent(status)}`), [status]);

  const rows = useMemo(() => (data ?? []).map((j) => {
    const as = j.assignments ?? [];
    return {
      ...j, md: j.totals.man_days, date_text: compactDates(j.dates ?? [], 99),
      inspector: as.map((a: any) => a.inspector_name).filter(Boolean).join(", ") || null,
      client_rate_text: rateText(as, "client_rate", "currency"),
      inspector_rate_text: rateText(as.filter((a: any) => !a.no_subcontractor), "inspector_rate", "inspector_currency"),
    };
  }), [data]);

  const cols: Col[] = [
    { key: "status", label: "Статус", render: (j) => <Pill status={j.status} /> },
    { key: "job_number", label: "Job №", cls: "mono" },
    { key: "client_name", label: "Клиент", render: (j) => <ClientChip name={j.client_name} /> },
    { key: "inspector", label: "Инспектор" },
    { key: "vendor", label: "Завод", cls: "wrap" },
    { key: "country", label: "Страна" },
    { key: "owner", label: "Чья", render: (j) => <OwnerChip initials={j.owner} /> },
    {
      key: "date_text", label: "Дата", text: (j) => compactDates(j.dates ?? [], 99) || null,
      render: (j) => (
        <button type="button" className={"date-cell" + (j.dates?.length ? "" : " empty-dates")} title="Открыть календарь дат инспекции"
          onClick={(e) => { e.stopPropagation(); setDates(j); }}>
          {j.dates?.length ? compactDates(j.dates)
            : (j.assignments ?? []).map((a: any) => a.dates_text).filter(Boolean).join("; ") || "указать даты"}
        </button>
      ),
    },
    { key: "md", label: "MD", align: "r", render: (j) => num(j.md, 1) },
    { key: "client_rate_text", label: "Ставка клиента", align: "r", sortNumeric: false, render: (j) => <Rate text={j.client_rate_text} /> },
    { key: "inspector_rate_text", label: "Ставка инспектора", align: "r", sortNumeric: false, render: (j) => <Rate text={j.inspector_rate_text} /> },
  ];

  const create = async (d: any) => {
    const job = await api.post("/jobs", Object.fromEntries(Object.entries(d).filter(([k]) => !k.startsWith("a_"))));
    if (d.a_inspector_id || d.a_dates_text || d.a_client_rate || d.a_inspector_rate) {
      await api.put(`/jobs/${job.id}/assignments/1`, {
        inspector_id: d.a_inspector_id, dates_text: d.a_dates_text, unit: "day", currency: d.a_currency, client_rate: d.a_client_rate ?? 0,
        inspector_rate: d.a_inspector_rate ?? 0, inspector_currency: d.a_inspector_currency, no_subcontractor: !d.a_inspector_rate && !d.a_inspector_id,
      });
    }
    nav(`/jobs/${job.id}`);
  };

  return (
    <div className="page">
      <header className="page-head">
        <h1>Табель</h1>
        <div className="head-actions">
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
            { key: "job_number", label: "Job" }, { key: "client_name", label: "Клиент" }, { key: "inspector", label: "Инспектор" }, { key: "vendor", label: "Завод" },
            { key: "country", label: "Страна" }, { key: "owner", label: "Чья" }, { key: "status", label: "Статус" }, { key: "date_text", label: "Даты" },
            { key: "md", label: "MD" }, { key: "client_rate_text", label: "Ставка клиента" }, { key: "inspector_rate_text", label: "Ставка инспектора" }])}>CSV</button>
          {can("write") && <button className="btn primary" onClick={() => setAdd(true)}>Новая работа</button>}
        </div>
        <ErrorLine error={error} />
        <DataTable rows={rows} cols={cols} onRowClick={(j) => nav(`/jobs/${j.id}`)} onVisible={setVisible}
          empty={loading ? "Загрузка…" : "Работ не найдено."} />
      </section>
      {cal && <JobsCalendar onClose={() => setCal(false)} />}
      {dates && <JobDatesModal job={dates} inspectors={inspectors} onClose={() => setDates(null)} onSaved={reload} />}
      {add && (
        <EditForm title="Новая работа" fields={[...jobFields, ...firstAssignment]}
          initial={{ status: "В работе", a_currency: "USD", a_inspector_currency: "USD" }} onCancel={() => setAdd(false)} onSave={create}
          onFieldChange={async (k, v) => {
            if (k === "client_id" && v) {
              const out: Record<string, unknown> = {};
              try { out.job_number = (await api.get(`/jobs/next-number?client_id=${v}`)).job_number; } catch { /* client without a code: type it in */ }
              const c = (await loadRef("clients")).find((x: any) => x.id === v);
              if (c?.default_currency) out.a_currency = c.default_currency;
              return out;
            }
          }} />
      )}
    </div>
  );
}
