import { useMemo, useState } from "react";
import { api, inr, money, monthLabel, thisMonth } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { ErrorLine, Modal, useAsync } from "../components/ui";
import { CURRENCIES, useRef_ } from "../refs";

export const SALES_STATUSES = ["Not Verified", "Отправлен клиенту", "Paid"];

const fields: Field[] = [
  { key: "number", label: "Номер", required: true, hint: "EBFI-2627-NNN" },
  { key: "date", label: "Дата", type: "date", required: true },
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, required: true },
  { key: "amount", label: "Сумма без GST", type: "money", currencyKey: "currency", required: true },
  { key: "gst_total", label: "GST, ₹", type: "money", form: false },
  { key: "status", label: "Статус", type: "status", options: SALES_STATUSES, required: true },
  { key: "received_amount", label: "Получено", type: "money", currencyKey: "currency", hint: "Для индийских клиентов — сумма после удержания TDS" },
  { key: "outstanding", label: "К получению", type: "money", currencyKey: "currency", form: false },
  { key: "payment_date", label: "Дата оплаты", type: "date" },
  { key: "fx_rate", label: "Курс к INR", type: "number", list: false, hint: "Пусто — возьмётся курс месяца инвойса" },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];

export default function Sales() {
  const [fromLines, setFromLines] = useState<null | (() => void)>(null);
  return (
    <div className="page">
      <header className="page-head"><div><h1>Инвойсы клиентам</h1>
        <p className="lede">GST считается автоматически для клиентов из Индии: CGST + SGST в своём штате, IGST — в другом. Для каждого такого инвойса создаётся запись в реестре TDS.</p></div></header>
      <CrudTable periodKey="date" endpoint="/sales-invoices" title="Реестр инвойсов" fields={fields} csvName="sales-invoices.csv"
        defaults={{ status: "Not Verified", date: new Date().toISOString().slice(0, 10), currency: "USD" }}
        toolbar={(_, reload) => <button className="btn" onClick={() => setFromLines(() => reload)}>Инвойс из строк работ</button>} />
      {fromLines && <FromLines onClose={() => setFromLines(null)} onDone={fromLines} />}
    </div>
  );
}

function FromLines({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const clients = useRef_("clients");
  const [month, setMonth] = useState(thisMonth());
  const [clientId, setClientId] = useState("");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [number, setNumber] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [err, setErr] = useState<string | null>(null);
  const { data } = useAsync(() => api.get<any[]>(`/lines?month=${month}`), [month]);
  const client = clients.find((c) => String(c.id) === clientId);
  const lines = useMemo(() => (data ?? []).filter((l) => !l.sales_invoice_id && (!client || l.client_name === client.name)), [data, client]);
  const chosen = lines.filter((l) => sel.has(l.id));
  const total = chosen.reduce((a, l) => a + l.calc.amount_currency, 0);

  const create = async () => {
    try {
      await api.post("/sales-invoices/from-lines", { line_ids: [...sel], number, date });
      onDone();
      onClose();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <Modal title="Инвойс из строк работ" onClose={onClose} wide>
      <div className="form-grid">
        <label className="field"><span>Месяц</span><input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
        <label className="field"><span>Клиент</span>
          <select value={clientId} onChange={(e) => { setClientId(e.target.value); setSel(new Set()); }}>
            <option value="">—</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
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
              {lines.length === 0 && <tr><td colSpan={6} className="empty">Нет строк без инвойса за {monthLabel(month)}.</td></tr>}
            </tbody>
          </table>
        </div>
        <label className="field"><span>Номер инвойса</span><input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="EBFI-2627-300" /></label>
        <label className="field"><span>Дата</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <p className="wide">Выбрано строк: <b>{chosen.length}</b>, сумма: <b>{chosen[0] ? money(total, chosen[0].currency) : "—"}</b></p>
        <ErrorLine error={err} />
        <div className="form-actions wide">
          <button className="btn ghost" onClick={onClose}>Отмена</button>
          <button className="btn primary" disabled={!chosen.length || !number} onClick={create}>Создать инвойс</button>
        </div>
      </div>
    </Modal>
  );
}

export { inr };
