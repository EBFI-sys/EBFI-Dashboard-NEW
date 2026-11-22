import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, dateLabel, money, monthLabel, num, pct, today } from "../api";
import { useAuth } from "../auth";
import { ClientChip, OwnerChip } from "../components/Chips";
import { JobDocuments } from "../components/Files";
import { EditForm, Field, FieldInput } from "../components/CrudTable";
import DataTable, { Col } from "../components/DataTable";
import { ErrorLine, Modal, Pill, Toast, useAsync } from "../components/ui";
import { CurrencySwitch, useCurrency } from "../currency";
import { CURRENCIES } from "../refs";
import { jobFields } from "./Jobs";

const F = (f: Field) => f;
const A = {
  inspector_id: F({ key: "inspector_id", label: "Инспектор", type: "ref", ref: "inspectors" }),
  dates_text: F({ key: "dates_text", label: "Даты инспекции", type: "dates" }),
  quantity: F({ key: "quantity", label: "Количество", type: "number" }),
  unit: F({ key: "unit", label: "Единица", type: "select", options: ["day", "hour", "ton", "lump"], required: true }),
  client_rate: F({ key: "client_rate", label: "Ставка клиента", type: "money" }),
  currency: F({ key: "currency", label: "Валюта", type: "select", options: CURRENCIES, required: true }),
  inspector_rate: F({ key: "inspector_rate", label: "Ставка инспектора", type: "money" }),
  inspector_currency: F({ key: "inspector_currency", label: "Валюта", type: "select", options: CURRENCIES, required: true }),
  overtime_client: F({ key: "overtime_client", label: "Overtime клиенту (сумма)", type: "money" }),
  overtime_inspector: F({ key: "overtime_inspector", label: "Overtime инспектору (сумма)", type: "money" }),
  no_subcontractor: F({ key: "no_subcontractor", label: "Без подрядчика", type: "bool" }),
  payment_method_id: F({ key: "payment_method_id", label: "Метод оплаты инспектору (для РКО)", type: "ref", ref: "payment-methods" }),
  rko_override_inr: F({ key: "rko_override_inr", label: "РКО вручную, ₹", type: "money" }),
  notes: F({ key: "notes", label: "Примечания к инспектору", type: "textarea" }),
};
const UNIT: Record<string, string> = { day: "дн.", hour: "ч", ton: "т", lump: "" };

function Assignment({ job, a, canWrite, canDelete, onSaved }: { job: any; a: any; canWrite: boolean; canDelete: boolean; onSaved: (j: any, msg: string) => void }) {
  const [d, setD] = useState<any>(a);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setD(a), [JSON.stringify(a)]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(d) !== JSON.stringify(a);
  const set = (k: string) => (v: any) => setD((x: any) => ({ ...x, [k]: v, ...(k === "dates_text" ? { quantity: null } : {}) }));
  const field = (f: Field, extra?: string) => (
    <label className={"field" + (extra ?? "") + (f.type === "bool" ? " inline" : "")}>
      <span>{f.label}</span>
      {canWrite ? <FieldInput f={f} value={d[f.key]} row={d} onChange={set(f.key)} /> : <span>{String(d[f.key] ?? "—")}</span>}
    </label>
  );
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const body = { ...d };
      for (const k of ["grp", "inspector_name", "dates", "months", "closed_months", "invoiced", "amount_client", "amount_inspector", "line_ids"]) delete body[k];
      onSaved(await api.put(`/jobs/${job.id}/assignments/${a.grp}`, body), "Сохранено");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    try {
      onSaved(await api.del(`/jobs/${job.id}/assignments/${a.grp}`), "Инспектор убран из работы");
    } catch (e: any) {
      setErr(e.message);
    }
  };
  const multiMonth = (a.months ?? []).length > 1;
  return (
    <div className="assign">
      <div className="assign-head">
        <h3>{a.inspector_name ?? (a.no_subcontractor ? "Без подрядчика" : "Инспектор не указан")}</h3>
        {a.closed_months?.length > 0 && <span className="pill mute">закрыт: {a.closed_months.map(monthLabel).join(", ")}</span>}
        {a.invoiced && <span className="pill ok">в инвойсе клиенту</span>}
        <div className="spacer" />
        <div className="sum-line">
          <span>Клиенту: <b>{money(a.amount_client, a.currency)}</b></span>
          <span>Инспектору: <b>{a.no_subcontractor ? "—" : money(a.amount_inspector, a.inspector_currency)}</b></span>
        </div>
      </div>
      <div className="form-grid">
        {field(A.inspector_id)}
        {field(A.dates_text, " wide")}
        <label className="field">
          <span>Количество{d.unit === "day" ? " (MD)" : ""}</span>
          {canWrite
            ? <input type="number" step="any" value={d.quantity ?? ""} placeholder="по датам" onChange={(e) => set("quantity")(e.target.value === "" ? null : e.target.value)} />
            : <span>{num(d.quantity, 2)}</span>}
          <small>{multiMonth ? "Даты в нескольких месяцах — дни считаются по датам" : "Пусто — по числу дат; можно указать 0.5"}</small>
        </label>
        {field(A.unit)}
        <label className="field"><span>Ставка клиента</span>
          <div className="money-pair">
            <FieldInput f={A.client_rate} value={d.client_rate} onChange={set("client_rate")} />
            <FieldInput f={A.currency} value={d.currency} onChange={set("currency")} />
          </div>
          <small>Инвойс клиенту — в этой валюте</small>
        </label>
        <label className="field"><span>Ставка инспектора</span>
          <div className="money-pair">
            <FieldInput f={A.inspector_rate} value={d.inspector_rate} onChange={set("inspector_rate")} />
            <FieldInput f={A.inspector_currency} value={d.inspector_currency} onChange={set("inspector_currency")} />
          </div>
          <small>Может отличаться от валюты клиента</small>
        </label>
        {field(A.overtime_client)}
        {field(A.overtime_inspector)}
        {field(A.payment_method_id)}
        {field(A.rko_override_inr)}
        {field(A.no_subcontractor)}
        {field(A.notes, " wide")}
      </div>
      <ErrorLine error={err} />
      {canWrite && (
        <div className="form-actions">
          {dirty && <span className="dirty-note">Есть несохранённые изменения</span>}
          {canDelete && <button className="btn ghost small" onClick={remove}>Убрать инспектора</button>}
          {dirty && <button className="btn ghost" onClick={() => setD(a)}>Отменить</button>}
          <button className="btn primary" disabled={!dirty || busy} onClick={save}>{busy ? "Сохраняю…" : "Сохранить"}</button>
        </div>
      )}
    </div>
  );
}

export default function JobCard() {
  const { id } = useParams();
  const { can } = useAuth();
  const { data: j0, error, reload } = useAsync(() => api.get(`/jobs/${id}`), [id]);
  const [j, setJ] = useState<any | null>(null);
  useEffect(() => setJ(j0), [j0]);
  const [editJob, setEditJob] = useState(false);
  const [remove, setRemove] = useState<null | "request" | "delete">(null);
  const nav = useNavigate();
  const loc = useLocation();
  const [toast, setToast] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { cur, conv, fmt } = useCurrency();
  const hist = useAsync(() => api.get(`/audit?table=jobs&record_id=${id}`), [id, j0]);

  if (error) return <div className="page"><ErrorLine error={error} /></div>;
  if (!j) return <div className="page muted">Загрузка…</div>;

  const total = (k: string) => {
    let t = 0;
    for (const l of j.lines) {
      const v = conv(l.calc[k], l.month);
      if (v == null) return null;
      t += v;
    }
    return t;
  };
  const saved = (nj: any, msg: string) => { setJ(nj); setToast(msg); };
  const addInspector = async () => {
    setErr(null);
    const last = j.assignments.at(-1) ?? {};
    try {
      saved(await api.post(`/jobs/${j.id}/assignments`, {
        unit: last.unit ?? "day", currency: last.currency ?? "USD", client_rate: last.client_rate ?? 0,
        inspector_currency: last.inspector_currency ?? last.currency ?? "USD", inspector_rate: 0, dates_text: last.dates_text ?? null,
      }), "Добавлен второй инспектор с теми же датами — поправьте его данные");
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const monthCols: Col[] = [
    { key: "month", label: "Месяц", render: (l) => <>{monthLabel(l.month)}{l.calc.closed && <span className="pill mute">закрыт</span>}</> },
    { key: "inspector_name", label: "Инспектор", render: (l) => l.inspector_name ?? "—" },
    { key: "dates_text", label: "Даты", cls: "wrap" },
    { key: "quantity", label: "Кол-во", align: "r", render: (l) => `${num(l.quantity, 2).replace(/\.00$/, "")} ${UNIT[l.unit] ?? l.unit}` },
    ...(["base_inr", "cost_inr", "admin_inr", "net_inr"] as const).map((k): Col => ({
      key: k, label: { base_inr: "Выручка", cost_inr: "Подряд", admin_inr: "Админка", net_inr: "Прибыль" }[k] + `, ${cur}`,
      align: "r", text: (l) => l.calc[k], total: undefined,
      render: (l) => k === "net_inr" ? <b className={(l.calc[k] ?? 0) < 0 ? "neg" : ""}>{fmt(l.calc[k], l.month)}</b> : fmt(l.calc[k], l.month),
    })),
    { key: "margin", label: "Маржа", align: "r", text: (l) => l.calc.margin, render: (l) => pct(l.calc.margin) },
  ];
  const owner = j.owner;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs">
            <button type="button" className="back-btn" onClick={() => (loc.key !== "default" ? nav(-1) : nav("/jobs"))} aria-label="Назад">‹ Назад</button>
            <Link to="/jobs">Табель</Link> /
          </p>
          <h1 className="mono">{j.job_number} <Pill status={j.status} /></h1>
        </div>
        <div className="head-actions">
          <CurrencySwitch />
          {can("write") && <button className="btn" onClick={() => setEditJob(true)}>Изменить данные работы</button>}
          {can("write") && <button className="btn ghost" onClick={() => setRemove("request")}>Вернуть в заявки</button>}
          {can("delete_work") && <button className="btn ghost danger-text" onClick={() => setRemove("delete")}>Удалить</button>}
        </div>
      </header>

      {j.flag && <LateBanner j={j} canClear={can("close_month")} onCleared={() => api.get(`/jobs/${j.id}`).then((nj) => saved(nj, "Отметка снята"))} />}

      <section className="card">
        <dl className="facts">
          <div><dt>Клиент</dt><dd><ClientChip name={j.client_name} /></dd></div>
          <div><dt>Завод</dt><dd>{j.vendor ?? "—"}</dd></div>
          <div><dt>Страна</dt><dd>{j.country ?? "—"}</dd></div>
          <div><dt>Чья</dt><dd><OwnerChip initials={owner} /></dd></div>
          <div className="facts-status"><dt>Статус работы</dt><dd><StatusSwitch j={j} canWrite={can("write")} onSaved={(nj) => saved({ ...j, ...nj }, `Статус: ${nj.status}`)} /></dd></div>
          <div><dt>Контакт клиента</dt><dd>{j.client_contact ?? "—"}</dd></div>
          <div><dt>Client Job Number</dt><dd>{j.client_job_number ?? "—"}</dd></div>
          {j.notes && <div style={{ gridColumn: "1 / -1" }}><dt>Примечания</dt><dd style={{ whiteSpace: "pre-wrap" }}>{j.notes}</dd></div>}
        </dl>
      </section>

      <section className="card">
        <div className="toolbar">
          <h2>Инспектор, даты и ставки</h2>
          <div className="spacer" />
          {can("write") && <button className="btn ghost small" onClick={addInspector}>+ Ещё инспектор на эту работу</button>}
        </div>
        <ErrorLine error={err} />
        {j.assignments.length === 0 && <p className="muted">Нет данных. Нажмите «+ Ещё инспектор», чтобы указать инспектора, даты и ставки.</p>}
        {j.assignments.map((a: any) => (
          <Assignment key={a.grp} job={j} a={a} canWrite={can("write")} canDelete={can("delete_work") && j.assignments.length > 1} onSaved={saved} />
        ))}
      </section>

      <JobDocuments job={j} canWrite={can("write")} onLinked={reload} />

      <div className="kpis">
        <div className="kpi card"><span className="kpi-label">Выручка</span><span className="kpi-value">{money(total("base_inr"), cur)}</span></div>
        <div className="kpi card"><span className="kpi-label">Чистая прибыль</span><span className={"kpi-value " + (j.totals.net_inr < 0 ? "bad" : "")}>{money(total("net_inr"), cur)}</span></div>
        <div className="kpi card"><span className="kpi-label">Человеко-дни</span><span className="kpi-value">{num(j.totals.man_days, 1)}</span></div>
      </div>

      <section className="card">
        <h2>Как работа попадает в финансовые результаты по месяцам</h2>
        <DataTable rows={j.lines} cols={monthCols} filters={false} empty="Пока пусто." />
        <p className="muted small">Считается автоматически из дат и ставок выше. Если даты идут через два месяца, работа делится между ними по дням.</p>
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Исходящие счета</h2>
          {j.sales_invoices.length === 0 ? <p className="muted">Нет. Создайте счёт в «Реестре исходящих счетов» → «Инвойс из работ».</p> : (
            <table><tbody>{j.sales_invoices.map((s: any) => (
              <tr key={s.id}><td className="mono">{s.number}</td><td>{dateLabel(s.date)}</td><td className="r">{money(s.amount, s.currency)}</td><td><Pill status={s.status} /></td></tr>
            ))}</tbody></table>
          )}
        </section>
        <section className="card">
          <h2>Входящие счета</h2>
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

      {editJob && <EditForm title="Данные работы" fields={jobFields} initial={j} onCancel={() => setEditJob(false)}
        onSave={async (d) => {
          const body = Object.fromEntries(Object.entries(d).filter(([k]) => !["lines", "assignments", "totals", "totals_by_month", "line_summary", "dates", "months", "sales_invoices", "inspector_invoices", "status"].includes(k)));
          await api.patch(`/jobs/${j.id}`, body); setEditJob(false); setToast("Сохранено"); reload();
        }} />}
      {remove && <RemoveJob job={j} mode={remove} onClose={() => setRemove(null)} onDone={(to) => nav(to)} />}
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}

function RemoveJob({ job, mode, onClose, onDone }: { job: any; mode: "request" | "delete"; onClose: () => void; onDone: (to: string) => void }) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (mode === "delete") await api.del(`/jobs/${job.id}`);
      else await api.post(`/jobs/${job.id}/to-request`);
      onDone(mode === "delete" ? "/jobs" : "/requests");
    } catch (e: any) {
      setErr(e.message);
      setBusy(false);
    }
  };
  return (
    <Modal title={mode === "delete" ? `Удалить работу ${job.job_number}?` : `Вернуть ${job.job_number} в заявки?`} onClose={onClose}>
      {mode === "delete" ? (
        <p>Работа исчезнет из Табеля, финансовых результатов и дашборда. Если она пришла из заявки, заявка останется, и её можно будет перенести снова.</p>
      ) : (
        <p>Работа уйдёт из Табеля, а заявка снова станет «В процессе» со всеми данными: клиент, завод, страна, даты, ставки, инспектор.
          Если работа была открыта без заявки, заявка создастся.</p>
      )}
      <p className="muted">Номер <b className="mono">{job.job_number}</b> останется использованным: в очереди номеров его больше не будет. При новом переносе работа получит следующий свободный номер.</p>
      <ErrorLine error={err} />
      <div className="form-actions">
        <button className="btn ghost" onClick={onClose}>Отмена</button>
        <button className={"btn " + (mode === "delete" ? "danger" : "primary")} disabled={busy} onClick={go}>
          {busy ? "…" : mode === "delete" ? "Удалить работу" : "Вернуть в заявки"}
        </button>
      </div>
    </Modal>
  );
}

/** Why the row is purple in the Табель: a closed month changed late, or the job left open after its month closed. */
function LateBanner({ j, canClear, onCleared }: { j: any; canClear: boolean; onCleared: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const when = j.late_edit_at ? new Date(j.late_edit_at).toLocaleString("ru-RU", { timeZone: "Asia/Kolkata", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  return (
    <div className="banner late">
      {j.overdue && <p><b>Работа не завершена</b>, хотя месяц её последней даты ({monthLabel(j.last_date.slice(0, 7))}) закрыт больше суток назад. Отметка уйдёт, когда работа получит статус «Завершен».</p>}
      {j.late_edit_at && (
        <p>
          <b>Изменён закрытый месяц</b> ({(j.late_edit_months ?? "").split(",").filter(Boolean).map(monthLabel).join(", ")}) позже суток после закрытия
          {j.late_edit_by ? ` — ${j.late_edit_by}` : ""}, {when}. Финансовые результаты этого месяца пересчитаны.
          {canClear && <button className="btn small" style={{ marginLeft: 10 }} onClick={async () => {
            try { await api.post(`/jobs/${j.id}/late-edit/clear`); onCleared(); } catch (e: any) { setErr(e.message); }
          }}>Проверено — снять отметку</button>}
        </p>
      )}
      {err && <p className="error">{err}</p>}
    </div>
  );
}

const STATUS_CLS: Record<string, string> = { "В работе": "warn", Пауза: "mute", Завершен: "ok" };

/** The job status right on the card: one click, saved at once. */
function StatusSwitch({ j, canWrite, onSaved }: { j: any; canWrite: boolean; onSaved: (job: any) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const future = j.last_date && j.last_date > today();
  const set = async (st: string) => {
    if (st === j.status || busy) return;
    setBusy(st);
    setErr(null);
    try {
      onSaved(await api.patch(`/jobs/${j.id}`, { status: st }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <div className="status-switch" role="radiogroup" aria-label="Статус работы">
        {["В работе", "Пауза", "Завершен"].map((st) => (
          <button key={st} type="button" role="radio" aria-checked={j.status === st} disabled={!canWrite || !!busy}
            className={STATUS_CLS[st] + (j.status === st ? " on" : "")} onClick={() => set(st)}
            title={st === "Завершен" && future ? `Есть даты впереди (последняя ${j.last_date.split("-").reverse().join(".")})` : undefined}>
            {busy === st ? "…" : st}
          </button>
        ))}
      </div>
      {j.status !== "Завершен" && j.dates_passed && <small className="late-hint">Все даты прошли — завершите работу</small>}
      {err && <small className="error">{err}</small>}
    </>
  );
}
