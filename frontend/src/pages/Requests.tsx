import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, money, today } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { ErrorLine, Modal } from "../components/ui";
import { CURRENCIES, useRef_ } from "../refs";

export const REQ_STATUSES = ["В процессе", "Принято в работу", "Выполнено", "Перенос", "Отмена"];
const CLOSED = ["Выполнено", "Отмена"];

function InspectorNames({ ids }: { ids: number[] | null }) {
  const rows = useRef_("inspectors");
  if (!ids?.length) return <>—</>;
  return <>{ids.map((id) => rows.find((r) => r.id === id)?.name ?? `#${id}`).join(", ")}</>;
}

export default function Requests() {
  const [show, setShow] = useState<"open" | "closed" | "all">("open");
  const [mk, setMk] = useState<any | null>(null);
  const inspectors = useRef_("inspectors");
  const nameOf = (id: number) => inspectors.find((r) => r.id === id)?.name ?? `#${id}`;

  const fields: Field[] = [
    { key: "received_date", label: "Дата получения", type: "date" },
    { key: "type", label: "Тип", type: "select", options: ["Inspection", "Audit", "Expediting"], required: true, optional: true },
    { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
    { key: "final_client", label: "Конечный клиент", list: false },
    { key: "country", label: "Страна", type: "suggest", ref: "countries", required: true },
    { key: "factory", label: "Завод / адрес", type: "suggest", ref: "vendors", wide: true },
    { key: "dates_text", label: "Даты", type: "dates" },
    { key: "client_rate", label: "Нам платят", type: "money", currencyKey: "client_currency" },
    { key: "client_currency", label: "Валюта клиента", type: "select", options: CURRENCIES, list: false },
    { key: "inspector_rate", label: "Ставка инспектора", type: "money", currencyKey: "inspector_currency", optional: true },
    { key: "inspector_currency", label: "Валюта инспектора", type: "select", options: CURRENCIES, list: false },
    { key: "inspector_ids", label: "Инспекторы (отправлены CV)", type: "multiref", ref: "inspectors", wide: true,
      hint: "Отметьте всех, чьи CV отправлены клиенту. При переносе в Табель выберете, кто поедет.",
      render: (r) => <InspectorNames ids={r.inspector_ids} />, text: (r) => (r.inspector_ids ?? []).map(nameOf).join(", ") || null },
    { key: "status", label: "Статус", type: "status", options: REQ_STATUSES, required: true },
    { key: "cancel_reason", label: "Причина отмены / переноса", wide: true, list: false },
    { key: "owner_id", label: "Чья", type: "ref", ref: "users", refLabel: "initials" },
    { key: "notes", label: "Примечания", type: "textarea", list: false },
  ];

  return (
    <div className="page">
      <header className="page-head"><h1>Заявки</h1></header>
      <CrudTable
        endpoint="/requests"
        title={{ open: "Активные заявки", closed: "Закрытые заявки", all: "Все заявки" }[show]}
        fields={fields}
        csvName="requests.csv"
        periodKey="received_date"
        periodLabel="Месяц получения"
        periodDefault="current"
        defaults={{ status: "В процессе", type: "Inspection", received_date: today(), client_currency: "USD", inspector_currency: "USD", inspector_ids: [] }}
        filter={(r) => show === "all" || (show === "open" ? !CLOSED.includes(r.status) : CLOSED.includes(r.status))}
        toolbar={() => (
          <div className="seg">
            {([["open", "Активные"], ["closed", "Закрытые"], ["all", "Все"]] as const).map(([k, l]) => (
              <button key={k} className={show === k ? "on" : ""} onClick={() => setShow(k)}>{l}</button>
            ))}
          </div>
        )}
        rowActions={(r, reload) =>
          r.job_id ? <Link className="btn small ghost" to={`/jobs/${r.job_id}`}>В табеле</Link>
            : !CLOSED.includes(r.status) && <button className="btn small" title="Перенести заявку в Табель" onClick={() => setMk({ r, reload })}>В Табель →</button>
        }
      />
      {mk && <CreateJob req={mk.r} onClose={() => setMk(null)} onDone={mk.reload} />}
    </div>
  );
}

function CreateJob({ req, onClose, onDone }: { req: any; onClose: () => void; onDone: () => void }) {
  const nav = useNavigate();
  const inspectors = useRef_("inspectors");
  const clients = useRef_("clients");
  const [no, setNo] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [pick, setPick] = useState<Set<number>>(new Set(req.inspector_ids?.length === 1 ? req.inspector_ids : req.inspector_id ? [req.inspector_id] : []));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get(`/jobs/next-number?client_id=${req.client_id}`).then((r) => setNo(r.job_number)).catch((e) => setHint(e.message));
  }, [req.client_id]);
  const client = clients.find((c) => c.id === req.client_id);
  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const job = await api.post(`/requests/${req.id}/create-job`, { job_number: no, inspector_ids: [...pick] });
      onDone();
      nav(`/jobs/${job.id}`);
    } catch (e: any) {
      setErr(e.message);
      setBusy(false);
    }
  };
  const cands: number[] = req.inspector_ids ?? (req.inspector_id ? [req.inspector_id] : []);
  return (
    <Modal title="Перенести заявку в Табель" onClose={onClose}>
      <form onSubmit={go} className="form-grid">
        <label className="field wide"><span>Job number</span>
          <input autoFocus value={no} onChange={(e) => setNo(e.target.value)} placeholder="26.19-478" className="mono" />
          <small>{hint ?? `Следующий свободный номер в регистре ${client?.name ?? "клиента"} (код ${client?.job_code ?? "—"}). Можно изменить.`}</small>
        </label>
        <div className="field wide">
          <span>Кто поедет на инспекцию</span>
          {cands.length === 0 ? <small>В заявке не выбраны инспекторы — укажете в карточке работы.</small> : (
            <div className="pick-list">
              {cands.map((id) => (
                <label key={id} className="check">
                  <input type="checkbox" checked={pick.has(id)} onChange={() => { const n = new Set(pick); n.has(id) ? n.delete(id) : n.add(id); setPick(n); }} />
                  {inspectors.find((r) => r.id === id)?.name ?? `#${id}`}
                </label>
              ))}
            </div>
          )}
        </div>
        <div className="transfer wide">
          <p className="muted small">Перенесётся в работу:</p>
          <dl>
            <dt>Клиент</dt><dd>{client?.name ?? "—"}{req.final_client ? ` · конечный клиент ${req.final_client}` : ""}</dd>
            <dt>Завод</dt><dd>{req.factory ?? "—"}</dd>
            <dt>Страна</dt><dd>{req.country ?? "—"}</dd>
            <dt>Даты</dt><dd>{req.dates_text ?? "—"}</dd>
            <dt>Ставка клиента</dt><dd>{req.client_rate != null ? money(req.client_rate, req.client_currency ?? "USD") : "—"}</dd>
            <dt>Ставка инспектора</dt><dd>{req.inspector_rate != null ? money(req.inspector_rate, req.inspector_currency ?? req.client_currency ?? "USD") : "—"}</dd>
          </dl>
        </div>
        <ErrorLine error={err} />
        <div className="form-actions wide">
          <button type="button" className="btn ghost" onClick={onClose}>Отмена</button>
          <button className="btn primary" disabled={busy || !no}>{busy ? "Создаю…" : "Создать работу"}</button>
        </div>
      </form>
    </Modal>
  );
}
