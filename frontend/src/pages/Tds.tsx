import { inr } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { Pill } from "../components/ui";

const fields: Field[] = [
  { key: "quarter", label: "Квартал", form: false },
  { key: "invoice_number", label: "Инвойс", form: false },
  { key: "invoice_date", label: "Дата", type: "date", form: false },
  { key: "client_name", label: "Клиент", form: false },
  { key: "taxable_inr", label: "База, ₹", type: "money", form: false },
  { key: "amount_inr", label: "TDS, ₹", type: "money", form: false },
  { key: "invoice_status", label: "Оплата инвойса", form: false, render: (r) => <Pill status={r.invoice_status} />, text: (r) => r.invoice_status },
  { key: "status", label: "Статус TDS", type: "status", options: ["Ожидается", "В Form 26AS", "Зачтён"], required: true },
  { key: "notes", label: "Примечания", type: "textarea" },
];

export default function Tds() {
  return (
    <div className="page">
      <header className="page-head"><div><h1>Реестр TDS</h1>
        <p className="lede">TDS, удержанный индийскими клиентами (10% от суммы без GST). Это зачёт по налогу, он не уменьшает прибыль. Записи создаются автоматически из инвойсов; здесь отмечается, отражён ли TDS в Form 26AS и зачтён ли.</p></div></header>
      <CrudTable periodKey="invoice_date" endpoint="/tds" title="Записи TDS" fields={fields} csvName="tds.csv" writeRight="write" allowCreate={false}
        toolbar={(rows) => <span className="muted">Ожидается: {inr(rows.filter((r) => r.status !== "Зачтён").reduce((a, r) => a + r.amount_inr, 0))}</span>} />
    </div>
  );
}
