import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, compactDates, downloadCsv, monthLabel, num, thisMonth } from "../api";
import { useAuth } from "../auth";
import { JobDatesModal, JobsCalendar, shiftMonth } from "../components/Calendar";
import { ClientChip, OwnerChip } from "../components/Chips";
import { EditForm, Field } from "../components/CrudTable";
import DataTable, { Col } from "../components/DataTable";
import { ErrorLine, Pill, useAsync, usePersisted } from "../components/ui";
import { OwnerFilter, ownerMatch } from "../components/OwnerFilter";
import { BusyWarning } from "../components/Busy";
import { CURRENCIES, loadRef, useRef_ } from "../refs";

export const jobFields: Field[] = [
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "job_number", label: "Job number", required: true, hint: "Подставляется по очереди номеров клиента; можно изменить" },
  { key: "client_contact", label: "Контакт клиента" },
  { key: "client_job_number", label: "Client Job Number" },
  { key: "vendor", label: "Завод (Vendor)", type: "suggest", ref: "vendors", wide: true, hint: "Начните вводить — система предложит заводы из справочника; новый завод добавится сам" },
  { key: "country", label: "Страна", type: "suggest", ref: "countries" },
  { key: "owner_id", label: "Чья", type: "ref", ref: "users", refLabel: "initials" },
  { key: "notes", label: "Примечания", type: "textarea" },
];

/** Inspector, dates and rates entered together with a new job (the first assignment). */
const firstAssignment: Field[] = [
  { key: "a_inspector_id", label: "Инспектор", type: "ref", ref: "inspectors" },
  { key: "a_dates_text", label: "Даты инспекции", type: "dates", required: true },
  { key: "a_client_rate", label: "Ставка клиента (за день)", type: "money" },
  { key: "a_currency", label: "Валюта клиента", type: "select", options: CURRENCIES, required: true },
  { key: "a_inspector_rate", label: "Ставка инспектора (за день)", type: "money" },
  { key: "a_inspector_currency", label: "Валюта инспектора", type: "select", options: CURRENCIES, required: true },
];

/** «Markus Ehrmann, Yurii Kondrus» → «Ehrmann, Kondrus» for the phone list */
export function surnames(names: string | null | undefined) {
  return (names ?? "").split(",").map((n) => n.trim().split(/\s+/).pop()).filter(Boolean).join(", ");
}

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
  const { can, me } = useAuth();
  const inspectorRows = useRef_("inspectors");
  const inspectors = useMemo(() => new Map(inspectorRows.map((i) => [i.id, i])), [inspectorRows]);
  // filters stay when you open a job and come back, switch sections or reopen the app
  const [status, setStatus] = usePersisted("jobs.status", "В работе,Пауза");
  const [month, setMonth] = usePersisted("jobs.month", thisMonth(), "session");
  const [owner, setOwner] = usePersisted("jobs.owner", "");
  const [q, setQ] = usePersisted("jobs.q", "", "session");
  const [add, setAdd] = useState(false);
  const [cal, setCal] = useState(false);
  const [dates, setDates] = useState<any | null>(null);
  const [visible, setVisible] = useState<any[]>([]);
  const unfinished = useAsync(() => month ? api.get<any[]>(`/jobs/unfinished?before=${month}`) : Promise.resolve([]), [month]);
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(`/jobs?status=${encodeURIComponent(status)}${month ? `&month=${month}` : ""}`), [status, month]);

  const rows = useMemo(() => (data ?? []).map((j) => {
    const as = j.assignments ?? [];
    const v = month ? j.view : null;  // the month's part of the job
    const ds: string[] = v ? v.dates : j.dates ?? [];
    return {
      ...j, md: v ? v.man_days : j.totals.man_days, ds, date_text: compactDates(ds, 99),
      inspector: as.map((a: any) => a.inspector_name).filter(Boolean).join(", ") || null,
      client_rate_text: rateText(as, "client_rate", "currency"),
      inspector_rate_text: rateText(as.filter((a: any) => !a.no_subcontractor), "inspector_rate", "inspector_currency"),
    };
  }).filter((j) => ownerMatch(owner, j.owner_id, me?.id)).filter((j) => !q || [j.job_number, j.client_name, j.inspector, j.vendor, j.country, j.client_job_number]
    .some((v) => v && String(v).toLowerCase().includes(q.toLowerCase()))), [data, month, q, owner, me?.id]);

  const cols: Col[] = [
    {
      key: "status", label: "Статус", mobile: "head", render: (j) => (
        <span className="status-cell"><Pill status={j.status} />
          {j.dates_passed && <span className="pill late-pill" title={`Последняя дата ${j.last_date.split("-").reverse().join(".")} прошла — завершите работу`}>даты прошли</span>}
        </span>
      ),
    },
    { key: "job_number", label: "Job №", cls: "mono", mobile: "head" },
    { key: "client_name", label: "Клиент", mobile: "head", render: (j) => <ClientChip name={j.client_name} /> },
    { key: "inspector", label: "Инспектор", mlist: true },
    { key: "vendor", label: "Завод", cls: "wrap", mobile: "wide" },
    { key: "country", label: "Страна" },
    { key: "owner", label: "Чья", render: (j) => <OwnerChip initials={j.owner} /> },
    {
      key: "date_text", mobile: "wide", mlist: true, label: month ? "Дата (" + monthLabel(month).split(" ")[0].toLowerCase() + ")" : "Дата", text: (j) => j.date_text || null,
      render: (j) => (
        <button type="button" className={"date-cell" + (j.ds?.length ? "" : " empty-dates")}
          title="Открыть календарь дат инспекции"
          onClick={(e) => { e.stopPropagation(); setDates(j); }}>
          {j.ds?.length ? compactDates(j.ds)
            : (j.assignments ?? []).map((a: any) => a.dates_text).filter(Boolean).join("; ") || "указать даты"}
        </button>
      ),
    },
    { key: "md", label: "MD", align: "r", render: (j) => num(j.md, 1) },
    { key: "client_rate_text", label: "Ставка клиента", align: "r", sortNumeric: false, render: (j) => <Rate text={j.client_rate_text} /> },
    { key: "inspector_rate_text", label: "Ставка инспектора", align: "r", sortNumeric: false, render: (j) => <Rate text={j.inspector_rate_text} /> },
  ];

  const create = async (d: any) => {
    const job = await api.post("/jobs", {
      ...Object.fromEntries(Object.entries(d).filter(([k]) => !k.startsWith("a_"))),
      assignment: {
        inspector_id: d.a_inspector_id, dates_text: d.a_dates_text, unit: "day", currency: d.a_currency, client_rate: d.a_client_rate ?? 0,
        inspector_rate: d.a_inspector_rate ?? 0, inspector_currency: d.a_inspector_currency, no_subcontractor: !d.a_inspector_rate && !d.a_inspector_id,
      },
    });
    nav(`/jobs/${job.id}`);
  };
  const mine = (unfinished.data ?? []).filter((u) => ownerMatch(owner, u.owner_id, me?.id));
  const months = useMemo(() => Array.from({ length: 19 }, (_, i) => shiftMonth(thisMonth(), 6 - i)), []);

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
            {[["В работе,Пауза", "Активные"], ["Завершен", "Завершенные"], ["", "Все"]].map(([v, l]) => (
              <button key={l} className={status === v ? "on" : ""} onClick={() => setStatus(v)}>{l}</button>
            ))}
          </div>
          <div className="month-pick" role="group" aria-label="Отчётный месяц">
            <button className="btn small ghost" disabled={!month} onClick={() => setMonth(shiftMonth(month, -1))} aria-label="Предыдущий месяц">‹</button>
            <select value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Отчётный месяц">
              {months.map((m) => <option key={m} value={m}>{monthLabel(m)}{m === thisMonth() ? " (текущий)" : ""}</option>)}
              <option value="">Все месяцы</option>
            </select>
            <button className="btn small ghost" disabled={!month} onClick={() => setMonth(shiftMonth(month, 1))} aria-label="Следующий месяц">›</button>
          </div>
          <OwnerFilter value={owner} onChange={setOwner} />
          <span className="muted">{loading ? "Загрузка…" : `${visible.length} работ`}</span>
          <div className="spacer" />
          <input className="search" type="search" placeholder="Поиск: номер, клиент, инспектор, завод" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn ghost" onClick={() => downloadCsv("tabel.csv", visible, [
            { key: "job_number", label: "Job" }, { key: "client_name", label: "Клиент" }, { key: "inspector", label: "Инспектор" }, { key: "vendor", label: "Завод" },
            { key: "country", label: "Страна" }, { key: "owner", label: "Чья" }, { key: "status", label: "Статус" }, { key: "date_text", label: "Даты" },
            { key: "md", label: "MD" }, { key: "client_rate_text", label: "Ставка клиента" }, { key: "inspector_rate_text", label: "Ставка инспектора" }])}>CSV</button>
          {can("write") && <button className="btn primary" onClick={() => setAdd(true)}>Новая работа</button>}
        </div>
        <ErrorLine error={error} />
        {mine.length > 0 && (
          <div className="banner late unfinished">
            <span>Не завершены работы прошлых месяцев ({mine.length}):</span>
            {mine.map((u) => (
              <button key={u.id} className="job-link mono" title={`Последний месяц работы — ${monthLabel(u.month)}`} onClick={() => nav(`/jobs/${u.id}`)}>{u.job_number}</button>
            ))}
          </div>
        )}
        {month && <p className="muted small table-note">{monthLabel(month)}: только работы с днями в этом месяце, даты и MD — за этот месяц.
          {" "}<span className="late-key" /> — изменён закрытый месяц или работа не завершена после закрытия месяца.</p>}
        <DataTable rows={rows} cols={cols} storageKey="jobs" mobileRow={(j) => (
          <div className="lrow lrow-job">
            <Pill status={j.status} />
            <b className="lrow-no mono">{j.job_number}</b>
            <span className="lrow-right"><ClientChip name={j.client_name} /></span>
            <span className="lrow-sub">{surnames(j.inspector) || "—"}</span>
            <span className="lrow-right lrow-dates">{j.ds?.length ? compactDates(j.ds) : "—"}</span>
          </div>
        )} onRowClick={(j) => nav(`/jobs/${j.id}`)} onVisible={setVisible}
          rowClass={(j) => (j.flag ? "late" : undefined)}
          rowTitle={(j) => j.overdue ? "Месяц закрыт больше суток назад, а работа не завершена"
            : j.late_edit_at ? "Закрытый месяц изменён позже суток после закрытия — проверьте в карточке" : undefined}
          loading={loading} empty={loading ? "Загрузка…" : "Работ не найдено."} />
      </section>
      {cal && <JobsCalendar onClose={() => setCal(false)} />}
      {dates && <JobDatesModal job={dates} inspectors={inspectors} onClose={() => setDates(null)} onSaved={reload} />}
      {add && (
        <EditForm title="Новая работа" fields={[...jobFields, ...firstAssignment]}
          initial={{ status: "В работе", a_currency: "USD", a_inspector_currency: "USD" }} onCancel={() => setAdd(false)} onSave={create}
          extra={(d) => <BusyWarning inspectorIds={[d.a_inspector_id]} datesText={d.a_dates_text} />}
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
