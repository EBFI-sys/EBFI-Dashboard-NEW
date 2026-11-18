import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import CrudTable, { Field } from "../components/CrudTable";
import { ErrorLine, Toast, useAsync } from "../components/ui";
import { CURRENCIES, REGIONS } from "../refs";

const clientFields: Field[] = [
  { key: "name", label: "Клиент (юрлицо)", required: true, hint: "Каждое юрлицо — отдельный клиент: TÜV Rheinland Oman, Qatar и India не объединяются" },
  { key: "legal_name", label: "Полное юр. название", wide: true },
  { key: "is_indian", label: "Клиент из Индии (GST и TDS)", type: "bool" },
  { key: "gstin", label: "GSTIN" },
  { key: "state", label: "Штат (для CGST/SGST или IGST)" },
  { key: "default_currency", label: "Валюта по умолчанию", type: "select", options: CURRENCIES },
  { key: "contact_name", label: "Контакт", list: false },
  { key: "contact_email", label: "Email контакта", list: false },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];
const inspectorFields: Field[] = [
  { key: "name", label: "Имя", required: true },
  { key: "country", label: "Страна" },
  { key: "specialization", label: "Специализация" },
  { key: "rate", label: "Обычная ставка", type: "money", currencyKey: "currency" },
  { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, list: false },
  { key: "email", label: "Email" },
  { key: "phone", label: "Телефон", list: false },
  { key: "payment_method_id", label: "Способ оплаты", type: "ref", ref: "payment-methods" },
  { key: "bank_details", label: "Банковские реквизиты", type: "textarea", list: false, hint: "Хранятся в зашифрованном виде; каждое изменение пишется в журнал" },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];
const countryFields: Field[] = [
  { key: "name", label: "Страна", required: true },
  { key: "region", label: "Регион", type: "select", options: REGIONS, required: true },
];
const pmFields: Field[] = [
  { key: "name", label: "Способ оплаты", required: true },
  { key: "rko_percent", label: "РКО, % от суммы подряда", type: "number" },
  { key: "rko_fixed_inr", label: "РКО фиксированно, ₹", type: "money" },
];
const fxFields: Field[] = [
  { key: "month", label: "Месяц (ГГГГ-ММ)", required: true },
  { key: "currency", label: "Валюта", type: "select", options: ["USD", "EUR", "GBP"], required: true },
  { key: "rate", label: "₹ за единицу (RBI, последний день месяца)", type: "number", required: true },
];

const TABS = [
  ["clients", "Клиенты"], ["inspectors", "Инспекторы"], ["fx", "Курсы"], ["settings", "Ставки налогов"],
  ["pm", "Способы оплаты"], ["countries", "Страны"],
] as const;

export default function References() {
  const [tab, setTab] = useState<string>("clients");
  return (
    <div className="page">
      <header className="page-head"><h1>Справочники</h1></header>
      <nav className="tabs">{TABS.map(([id, l]) => <button key={id} aria-selected={tab === id} onClick={() => setTab(id)}>{l}</button>)}</nav>
      {tab === "clients" && <CrudTable endpoint="/clients" title="Клиенты" fields={clientFields} refName="clients" defaults={{ default_currency: "USD" }} csvName="clients.csv" />}
      {tab === "inspectors" && <CrudTable endpoint="/inspectors" title="Инспекторы" fields={inspectorFields} refName="inspectors" defaults={{ currency: "USD" }} csvName="inspectors.csv" />}
      {tab === "fx" && <CrudTable endpoint="/fx-rates" title="Курсы к INR" fields={fxFields} writeRight="settings" defaults={{ currency: "USD" }} />}
      {tab === "settings" && <TaxSettings />}
      {tab === "pm" && <CrudTable endpoint="/payment-methods" title="Способы оплаты и РКО" fields={pmFields} refName="payment-methods" />}
      {tab === "countries" && <CrudTable endpoint="/countries" title="Страны и регионы" fields={countryFields} defaults={{ region: "Europe" }} />}
    </div>
  );
}

function TaxSettings() {
  const { can } = useAuth();
  const { data, error, setData } = useAsync(() => api.get("/settings"), []);
  const [toast, setToast] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!data) return <ErrorLine error={error} />;
  const L: Record<string, string> = { gst_rate: "GST (доля, 0.18 = 18%)", tds_rate: "TDS (доля, 0.10 = 10%)", admin_rate: "Админка (доля от B, 0.18 = 18%)", company_state: "Штат EBFI Privat Limited" };
  return (
    <section className="card narrow">
      <h2>Ставки налогов</h2>
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
