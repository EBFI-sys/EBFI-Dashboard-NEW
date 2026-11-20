import { ClientChip, ColorInput, defaultClientColor } from "../components/Chips";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import CrudTable, { Field } from "../components/CrudTable";
import { ErrorLine, Toast, useAsync } from "../components/ui";
import { CURRENCIES, REGIONS } from "../refs";

const clientFields: Field[] = [
  { key: "name", label: "Клиент (юрлицо)", required: true, hint: "Каждое юрлицо — отдельный клиент: TÜV Rheinland Oman, Qatar и India не объединяются" },
  { key: "color", label: "Цвет метки", wide: true, text: (r) => r.color,
    render: (r) => <ClientChip name={r.name} color={r.color} />,
    input: ({ value, onChange, row }) => <ColorInput value={value} onChange={onChange} fallback={defaultClientColor(row.name ?? "")} /> },
  { key: "job_code", label: "Код в Job number (КК)", hint: "26.19-478 → код 19. Номер новой работы присваивается по очереди этого кода" },
  { key: "legal_name", label: "Полное юр. название", wide: true },
  { key: "address", label: "Адрес для инвойса", type: "textarea", list: false, hint: "Юридический адрес клиента — как он будет напечатан в инвойсе" },
  { key: "is_indian", label: "Клиент из Индии (GST и TDS)", type: "bool" },
  { key: "wht", label: "Удерживает WHT 5% (на счёт приходит сумма минус WHT)", type: "bool" },
  { key: "gstin", label: "GSTIN" },
  { key: "state", label: "Штат (для CGST/SGST или IGST)" },
  { key: "default_currency", label: "Валюта по умолчанию", type: "select", options: CURRENCIES },
  { key: "contact_name", label: "Контакт", list: false },
  { key: "contact_email", label: "Email контакта", list: false },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];
const finalClientFields: Field[] = [
  { key: "name", label: "Финальный клиент", required: true, wide: true },
  { key: "notes", label: "Примечания", type: "textarea" },
];
const inspectorFields: Field[] = [
  { key: "name", label: "Имя", required: true },
  { key: "country", label: "Страна", type: "suggest", ref: "countries" },
  { key: "specialization", label: "Специализация" },
  { key: "rate", label: "Обычная ставка", type: "money", currencyKey: "currency" },
  { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, list: false },
  { key: "email", label: "Email" },
  { key: "phone", label: "Телефон", list: false },
  { key: "payment_method_id", label: "Метод оплаты", type: "ref", ref: "payment-methods" },
  { key: "bank_details", label: "Банковские реквизиты", type: "textarea", list: false, hint: "Хранятся в зашифрованном виде; каждое изменение пишется в журнал" },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];
const countryFields: Field[] = [
  { key: "name", label: "Страна", required: true },
  { key: "region", label: "Регион", type: "select", options: REGIONS, required: true },
];
const pmFields: Field[] = [
  { key: "name", label: "Метод оплаты", required: true },
  { key: "rko_percent", label: "РКО, % от суммы подряда", type: "number" },
  { key: "rko_fixed_inr", label: "РКО фиксированно, ₹", type: "money" },
];
const vendorFields: Field[] = [
  { key: "name", label: "Завод / предприятие", required: true, wide: true },
  { key: "country", label: "Страна", type: "suggest", ref: "countries" },
  { key: "notes", label: "Примечания", type: "textarea" },
];
const fxFields: Field[] = [
  { key: "month", label: "Месяц (ГГГГ-ММ)", required: true },
  { key: "currency", label: "Валюта", type: "select", options: ["USD", "EUR", "GBP"], required: true },
  { key: "rate", label: "₹ за единицу (RBI, последний день месяца)", type: "number", required: true },
];

const TABS = [
  ["clients", "Клиент"], ["final", "Финальный клиент"], ["inspectors", "Инспектор"], ["vendors", "Завод (Vendor)"], ["fx", "Курс валют"],
  ["settings", "Налоги и нумерация"], ["pm", "Метод оплаты"], ["countries", "Страна"],
] as const;

export default function References() {
  const [tab, setTab] = useState<string>("clients");
  return (
    <div className="page">
      <header className="page-head"><h1>Справочники</h1></header>
      <nav className="tabs">{TABS.map(([id, l]) => <button key={id} aria-selected={tab === id} onClick={() => setTab(id)}>{l}</button>)}</nav>
      {tab === "clients" && <CrudTable columnFilters={false} endpoint="/clients" title="Клиент" fields={clientFields} refName="clients" defaults={{ default_currency: "USD", wht: false, is_indian: false }} csvName="clients.csv" deleteRight="delete_work" />}
      {tab === "final" && <CrudTable columnFilters={false} endpoint="/final-clients" title="Финальный клиент" fields={finalClientFields} refName="final-clients" csvName="final-clients.csv" deleteRight="delete_work" />}
      {tab === "inspectors" && <CrudTable columnFilters={false} endpoint="/inspectors" title="Инспектор" fields={inspectorFields} refName="inspectors" defaults={{ currency: "USD" }} csvName="inspectors.csv" />}
      {tab === "vendors" && <CrudTable columnFilters={false} endpoint="/vendors" title="Завод (Vendor)" fields={vendorFields} refName="vendors" csvName="vendors.csv" />}
      {tab === "fx" && <CrudTable columnFilters={false} endpoint="/fx-rates" title="Курс валют к INR" fields={fxFields} writeRight="settings" defaults={{ currency: "USD" }} />}
      {tab === "settings" && <TaxSettings />}
      {tab === "pm" && <CrudTable columnFilters={false} endpoint="/payment-methods" title="Метод оплаты и РКО" fields={pmFields} refName="payment-methods" />}
      {tab === "countries" && <CrudTable columnFilters={false} endpoint="/countries" title="Страна и регион" fields={countryFields} defaults={{ region: "Europe" }} />}
    </div>
  );
}

function TaxSettings() {
  const { can } = useAuth();
  const { data, error, setData } = useAsync(() => api.get("/settings"), []);
  const [toast, setToast] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!data) return <ErrorLine error={error} />;
  const L: Record<string, string> = { gst_rate: "GST (доля, 0.18 = 18%)", tds_rate: "TDS (доля, 0.10 = 10%)", admin_rate: "Админка (доля от B, 0.18 = 18%)", company_state: "Штат EBFI Privat Limited", wht_rate: "WHT (доля, 0.05 = 5%) — для клиентов с отметкой «Удерживает WHT»", sales_invoice_last: "Автонумерация инвойсов: последний выданный номер (NNN). Пусто — номера вводятся вручную" };
  return (
    <section className="card narrow">
      <h2>Ставки налогов и нумерация</h2>
      <p className="muted">Меняются только для открытых месяцев: в закрытых месяцах ставки зафиксированы.</p>
      <div className="form-grid">
        {Object.keys(L).map((k) => (
          <label key={k} className="field wide"><span>{L[k]}</span>
            <input value={data[k]} disabled={!can("settings")} onChange={(e) => setData({ ...data, [k]: e.target.value })} />
          </label>
        ))}
        <ErrorLine error={err} />
        {can("settings") && <div className="form-actions wide"><button className="btn primary" onClick={async () => {
          try { setData(await api.put("/settings", data)); setToast("Сохранено"); } catch (e: any) { setErr(e.message); }
        }}>Сохранить</button></div>}
      </div>
      <Toast text={toast} onDone={() => setToast(null)} />
    </section>
  );
}
