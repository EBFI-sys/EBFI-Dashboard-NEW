import { useState } from "react";
import { api, money } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { Pill } from "../components/ui";
import { CURRENCIES } from "../refs";

const fields: Field[] = [
  { key: "inspector_id", label: "Инспектор", type: "ref", ref: "inspectors", required: true },
  { key: "number", label: "Номер счёта" },
  { key: "invoice_date", label: "Дата счёта", type: "date" },
  { key: "job_ids", label: "Работы (EBFI №)", type: "multiref", ref: "jobs", refLabel: "job_number", list: false },
  { key: "job_numbers", label: "EBFI №", form: false, render: (r) => r.job_numbers?.join(", ") || "—" },
  { key: "dates_text", label: "Даты", list: false },
  { key: "days", label: "Дней", type: "number" },
  { key: "rate", label: "Ставка", type: "money", currencyKey: "currency", list: false },
  { key: "amount", label: "Сумма", type: "money", currencyKey: "currency", required: true,
    render: (r) => (
      <span title={r.expected_amount != null && Math.abs(r.expected_amount - r.amount) > 1 ? `По строкам работ: ${money(r.expected_amount, r.currency)}` : ""}>
        {money(r.amount, r.currency)}{r.expected_amount != null && Math.abs(r.expected_amount - r.amount) > 1 && <span className="pill warn" style={{ marginLeft: 6 }}>≠ строкам</span>}
      </span>
    ) },
  { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, required: true },
  { key: "payment_method_id", label: "Способ оплаты", type: "ref", ref: "payment-methods" },
  { key: "paid", label: "Оплачено", type: "bool", render: (r) => <Pill status={r.paid ? "Оплачено" : "К оплате"} /> },
  { key: "paid_date", label: "Дата оплаты", type: "date" },
  { key: "comment", label: "Комментарий", type: "textarea", list: false },
];

export default function Payouts() {
  const [show, setShow] = useState<"open" | "all">("open");
  return (
    <div className="page">
      <header className="page-head"><div><h1>Счета инспекторов</h1>
        <p className="lede">Инспекторы присылают свои счета — здесь их регистрируют, прикладывают PDF и отмечают оплату. Пометка «≠ строкам» значит, что сумма не совпадает с MD × ставка в привязанных работах.</p></div></header>
      <CrudTable periodKey="invoice_date" endpoint="/inspector-invoices" title={show === "open" ? "К оплате" : "Все счета"} fields={fields} csvName="inspector-invoices.csv"
        defaults={{ currency: "USD", paid: false, invoice_date: new Date().toISOString().slice(0, 10), job_ids: [] }}
        filter={(r) => show === "all" || !r.paid}
        toolbar={() => (
          <div className="seg">
            <button className={show === "open" ? "on" : ""} onClick={() => setShow("open")}>К оплате</button>
            <button className={show === "all" ? "on" : ""} onClick={() => setShow("all")}>Все</button>
          </div>
        )}
        rowActions={(r, reload) => <FileCell row={r} reload={reload} />} />
    </div>
  );
}

function FileCell({ row, reload }: { row: any; reload: () => void }) {
  const [busy, setBusy] = useState(false);
  if (row.has_file) return <a className="btn small ghost" href={`/api/inspector-invoices/${row.id}/file`} target="_blank" rel="noreferrer">PDF</a>;
  return (
    <label className="btn small ghost file-btn">
      {busy ? "…" : "Загрузить PDF"}
      <input type="file" accept=".pdf,.png,.jpg,.jpeg" hidden onChange={async (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        setBusy(true);
        const fd = new FormData();
        fd.append("file", f);
        try { await api.post(`/inspector-invoices/${row.id}/file`, fd); reload(); } catch (err: any) { alert(err.message); } finally { setBusy(false); }
      }} />
    </label>
  );
}
