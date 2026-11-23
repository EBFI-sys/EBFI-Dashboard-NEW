import { useEffect, useMemo, useState } from "react";
import { api, inr, money, monthLabel, thisMonth, today } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { InvoiceFile } from "../components/Files";
import { FileText } from "lucide-react";
import { ErrorLine, Modal, Pill, useAsync } from "../components/ui";
import { CURRENCIES, useRef_ } from "../refs";

export const SALES_STATUSES = ["Not Verified", "Отправлен клиенту", "Paid"];

const fields: Field[] = [
  { key: "number", label: "Номер", required: true, hint: "EBFI-2627-NNN. Когда включена автонумерация, подставляется следующий по порядку" },
  { key: "date", label: "Дата", type: "date", required: true },
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, required: true },
  { key: "amount", label: "Сумма без GST", type: "money", currencyKey: "currency", required: true },
  { key: "gst_total", label: "GST, ₹", type: "money", form: false },
  { key: "wht", label: "WHT", type: "money", currencyKey: "currency", form: false, optional: true },
  { key: "status", label: "Статус", type: "status", options: SALES_STATUSES, required: true,
    render: (r) => r.credit_note ? <span className="pill bad" title="Сторнирован кредит-нотой">{r.credit_note}</span> : <Pill status={r.status} /> },
  { key: "received_amount", label: "Получено", type: "money", currencyKey: "currency", hint: "Для индийских клиентов — сумма после удержания TDS" },
  { key: "outstanding", label: "К получению", type: "money", currencyKey: "currency", form: false },
  { key: "payment_date", label: "Дата оплаты", type: "date" },
  { key: "fx_rate", label: "Курс к INR", type: "number", list: false, hint: "Пусто — возьмётся курс месяца инвойса" },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];

export default function Sales() {
  const [fromLines, setFromLines] = useState<null | (() => void)>(null);
  const [doc, setDoc] = useState<{ inv: any; reload: () => void } | null>(null);
  const next = useAsync(() => api.get("/sales-invoices/next-number"), [fromLines]);
  return (
    <div className="page">
      <header className="page-head"><div><h1>Реестр исходящих счетов</h1>
        <p className="lede">GST считается автоматически для клиентов из Индии: CGST + SGST в своём штате, IGST — в другом. Для каждого такого инвойса создаётся запись в реестре TDS.</p></div></header>
      <CrudTable periodKey="date" endpoint="/sales-invoices" title="Реестр инвойсов" fields={fields} csvName="sales-invoices.csv"
        defaults={{ status: "Not Verified", date: today(), currency: "USD", number: next.data?.number }}
        toolbar={(_, reload) => <button className="btn" onClick={() => setFromLines(() => () => { reload(); next.reload(); })}>Инвойс из работ</button>}
        rowActions={(r, reload) => <>
          {r.line_ids?.length > 0 && <button className="btn small" title={r.template ? `Шаблон: ${r.template}` : "Шаблон клиента не выбран"}
            onClick={() => setDoc({ inv: r, reload })}><FileText size={13} aria-hidden />Word / PDF</button>}
          <InvoiceFile url={r.file_url} uploadUrl={`/api/sales-invoices/${r.id}/file`} reload={reload} />
        </>} />
      {fromLines && <FromLines onClose={() => setFromLines(null)} onDone={fromLines} />}
      {doc && <InvoiceDoc inv={doc.inv} onClose={() => setDoc(null)} onDone={doc.reload} />}
    </div>
  );
}

function FromLines({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const clients = useRef_("clients");
  const [month, setMonth] = useState(thisMonth());
  const [clientId, setClientId] = useState("");
  const [cur, setCur] = useState("");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [number, setNumber] = useState("");
  const [date, setDate] = useState("");
  const [split, setSplit] = useState(true);
  const [plan, setPlan] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { data } = useAsync(() => api.get<any[]>(`/lines?month=${month}`), [month]);
  const client = clients.find((c) => String(c.id) === clientId);
  const all = useMemo(() => (data ?? []).filter((l) => !l.sales_invoice_id && (!client || l.client_name === client.name)), [data, client]);
  const curs = [...new Set(all.map((l) => l.currency))].sort();
  const lines = all.filter((l) => !cur || l.currency === cur);
  useEffect(() => {
    api.get(`/sales-invoices/next-number${date ? `?on=${date}` : ""}`).then((r) => r.number && setNumber((n) => (n && !n.startsWith("EBFI-") ? n : r.number))).catch(() => undefined);
  }, [date]);
  const chosen = lines.filter((l) => sel.has(l.id));
  const mixed = !split && new Set(chosen.map((l) => l.currency)).size > 1;
  useEffect(() => {  // the client's template, rules, invoice date and how the lines will be split
    if (!sel.size) { setPlan(null); return; }
    const t = setTimeout(() => api.post("/sales-invoices/from-lines/plan", { line_ids: [...sel], split }).then((p) => { setPlan(p); setDate((d) => d || p.date || ""); }).catch(() => setPlan(null)), 250);
    return () => clearTimeout(t);
  }, [sel, split]);

  const create = async () => {
    try {
      const made = await api.post<any[]>("/sales-invoices/from-lines", { line_ids: [...sel], number, date: date || undefined, split });
      onDone();
      onClose();
      if (made.length > 1) alert(`Создано инвойсов: ${made.length} (${made.map((i) => i.number).join(", ")})`);
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <Modal title="Инвойс из работ" onClose={onClose} wide>
      <div className="form-grid">
        <label className="field"><span>Месяц</span><input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
        <label className="field"><span>Клиент</span>
          <select value={clientId} onChange={(e) => { setClientId(e.target.value); setSel(new Set()); }}>
            <option value="">—</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="field"><span>Валюта работы</span>
          <select value={cur} onChange={(e) => { setCur(e.target.value); setSel(new Set()); }}>
            <option value="">Все валюты</option>{(curs.length ? curs : ["USD", "EUR", "GBP", "INR"]).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <div className="wide table-wrap tall">
          <table>
            <thead><tr><th /><th>Job №</th><th>Клиент</th><th>Инспектор</th><th>Даты</th><th className="r">Сумма</th></tr></thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id}>
                  <td><input type="checkbox" checked={sel.has(l.id)} onChange={(e) => { const n = new Set(sel); e.target.checked ? n.add(l.id) : n.delete(l.id); setSel(n); }} /></td>
                  <td className="mono">{l.job_number}</td><td>{l.client_name}</td><td>{l.inspector_name ?? "—"}</td><td className="wrap">{l.dates_text}</td>
                  <td className="r">{money(l.calc.amount_currency, l.currency)}</td>
                </tr>
              ))}
              {lines.length === 0 && <tr><td colSpan={6} className="empty">Нет работ без инвойса за {monthLabel(month)}.</td></tr>}
            </tbody>
          </table>
        </div>
        {plan && (
          <div className="wide plan-box">
            <p><b>{plan.template ? `Шаблон: ${plan.template}` : "У клиента не выбран шаблон инвойса (Справочники → Клиент)"}</b>
              {plan.notes?.length > 0 && <span className="muted small"> · {plan.notes.join(" · ")}</span>}</p>
            <label className="check"><input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} /> Разбить по правилу клиента</label>
            {plan.groups?.length > 0 && (
              <ul className="plan-list">
                {plan.groups.map((g: any, i: number) => (
                  <li key={i}><span className="mono">{i === 0 ? number || "—" : `+${i}`}</span> {g.jobs.join(", ")} — <b>{money(g.amount, g.currency)}</b></li>
                ))}
              </ul>
            )}
            {plan.groups?.length > 1 && <p className="muted small">Будет создано {plan.groups.length} инвойса(ов) с номерами подряд.</p>}
          </div>
        )}
        <label className="field"><span>Номер инвойса</span><input className="mono" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="EBFI-2627-300" />
          <small>{number ? "Следующий по порядку; можно изменить" : "Автонумерация не включена — введите номер"}</small></label>
        <label className="field"><span>Дата инвойса</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          <small>По правилу клиента: последний день месяца работ (морские сюрвеи и DITH — день выставления)</small></label>
        <p className="wide">Выбрано строк: <b>{chosen.length}</b>, сумма: <b>{chosen.length ? Object.entries(chosen.reduce((a: Record<string, number>, l) => ({ ...a, [l.currency]: (a[l.currency] ?? 0) + l.calc.amount_currency }), {})).map(([c, v]) => money(v as number, c)).join(" + ") : "—"}</b></p>
        <ErrorLine error={err} />
        <div className="form-actions wide">
          <button className="btn ghost" onClick={onClose}>Отмена</button>
          {mixed && <span className="dirty-note">Выбраны работы в разных валютах — включите разбиение или выберите одну валюту</span>}
          <button className="btn primary" disabled={!chosen.length || !number || mixed} onClick={create}>
            {plan?.groups?.length > 1 ? `Создать ${plan.groups.length} инвойса(ов)` : "Создать инвойс"}</button>
        </div>
      </div>
    </Modal>
  );
}

/** The invoice as a Word file (+ PDF, + Annexure for TUV Rheinland) from the client's template, saved to OneDrive. */
function InvoiceDoc({ inv, onClose, onDone }: { inv: any; onClose: () => void; onDone: () => void }) {
  const { data, error, reload } = useAsync(() => api.get(`/sales-invoices/${inv.id}/document`), [inv.id]);
  const [extra, setExtra] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (data && extra === null) setExtra(data.extra_lines ?? []); }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const make = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await api.post(`/sales-invoices/${inv.id}/document`, { extra_lines: extra ?? [] }));
      reload();
      onDone();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const s = res?.summary ?? data?.summary;
  const warnings: string[] = res?.warnings ?? data?.warnings ?? [];
  const urls = res ?? data ?? {};
  const dl = (k: string) => `/api/sales-invoices/${inv.id}/document/${k}`;
  return (
    <Modal title={`Инвойс ${inv.number} · Word / PDF`} onClose={onClose} wide>
      <ErrorLine error={error} />
      {data && (
        <div className="doc-box">
          <p><b>{data.template ?? "Шаблон не выбран"}</b>{data.jobs?.length > 0 && <span className="muted"> · работы {data.jobs.join(", ")}</span>}</p>
          {data.notes?.length > 0 && <p className="muted small">{data.notes.join(" · ")}</p>}
          {s && (
            <dl className="facts">
              <div><dt>Дата</dt><dd>{s.date.split("-").reverse().join(".")}</dd></div>
              <div><dt>Строк</dt><dd>{s.items}</dd></div>
              <div><dt>Сумма</dt><dd>{money(s.total, s.currency)}</dd></div>
              {s.base_inr != null && <div><dt>В рупиях</dt><dd>{inr(s.base_inr)}</dd></div>}
              {s.gst > 0 && <div><dt>GST</dt><dd>{inr(s.gst)}</dd></div>}
              {s.grand_inr != null && <div><dt>Итого с GST</dt><dd><b>{inr(s.grand_inr)}</b></dd></div>}
              {s.wht > 0 && <div><dt>Удержание 5%</dt><dd>{money(s.wht, s.currency)} → к оплате {money(s.total - s.wht, s.currency)}</dd></div>}
            </dl>
          )}
          {data.protos?.length > 1 && extra && (
            <div className="extra-lines">
              <p className="small"><b>Дополнительные строки</b> <span className="muted">— лабораторный анализ, draft survey, пестициды и т.п.</span></p>
              {extra.map((x, i) => (
                <div key={i} className="extra-row">
                  <select value={x.proto} onChange={(e) => setExtra(extra.map((y, j) => (j === i ? { ...y, proto: Number(e.target.value) } : y)))}>
                    {data.protos.map((p: any) => <option key={p.idx} value={p.idx}>{p.label} ({p.unit})</option>)}
                  </select>
                  <input type="number" step="any" placeholder="Кол-во" value={x.qty ?? ""} onChange={(e) => setExtra(extra.map((y, j) => (j === i ? { ...y, qty: e.target.value } : y)))} />
                  <input type="number" step="any" placeholder="Цена" value={x.rate ?? ""} onChange={(e) => setExtra(extra.map((y, j) => (j === i ? { ...y, rate: e.target.value } : y)))} />
                  <button className="btn small ghost" onClick={() => setExtra(extra.filter((_, j) => j !== i))} aria-label="Убрать строку">×</button>
                </div>
              ))}
              <div className="form-actions" style={{ justifyContent: "flex-start", marginTop: 0 }}>
                <button className="btn small ghost" onClick={() => setExtra([...extra, { proto: 1, qty: "", rate: "", job: data.jobs?.[0] }])}>+ строка</button>
                {data.suggested_extra?.length > 0 && <button className="btn small" title="По грузу, тоннажу и стране из карточки работы: лоты = тоннаж / 5000 вверх, ставки из инструкции"
                  onClick={() => setExtra(data.suggested_extra)}>Подставить по грузу и тоннажу</button>}
              </div>
            </div>
          )}
          {warnings.length > 0 && <ul className="problems">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
          <ErrorLine error={err} />
          <div className="form-actions" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
            <button className="btn primary" disabled={busy || !data.template} onClick={make}>{busy ? "Формирую…" : urls.doc_url ? "Сформировать заново" : "Сформировать Word и PDF"}</button>
            <a className="btn ghost" href={dl("docx")}>Скачать Word</a>
            <a className="btn ghost" href={dl("pdf")}>Скачать PDF</a>
            {data.annexure && <a className="btn ghost" href={dl("xlsx")}>Скачать Annexure</a>}
          </div>
          {(urls.doc_url || urls.pdf_url) && (
            <p className="small">На сервере (Outgoing Invoice Register):{" "}
              {urls.doc_url && <a href={urls.doc_url} target="_blank" rel="noreferrer">Word</a>}
              {urls.pdf_url && <> · <a href={urls.pdf_url} target="_blank" rel="noreferrer">PDF</a></>}
              {urls.annex_url && <> · <a href={urls.annex_url} target="_blank" rel="noreferrer">Annexure</a></>}</p>
          )}
          <p className="muted small">Повторное формирование заменяет файлы — номер инвойса сохраняется. Мелкие правки можно сделать в Word прямо на OneDrive.</p>
        </div>
      )}
    </Modal>
  );
}

export { inr };
