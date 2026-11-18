import { useState } from "react";
import { api } from "../api";
import { ErrorLine, useAsync } from "../components/ui";

const TABLES: Record<string, string> = {
  "": "Все", inspectors: "Инспекторы (вкл. реквизиты)", inspector_invoices: "Счета инспекторов", sales_invoices: "Инвойсы клиентам",
  jobs: "Работы", job_lines: "Строки P&L", requests: "Заявки", clients: "Клиенты", fx_rates: "Курсы", users: "Пользователи",
};

export default function Audit() {
  const [table, setTable] = useState("");
  const { data, error, loading } = useAsync(() => api.get<any[]>(`/audit?limit=500${table ? `&table=${table}` : ""}`), [table]);
  return (
    <div className="page">
      <header className="page-head"><div><h1>Журнал изменений</h1>
        <p className="lede">Кто, когда и что поменял. Перед пачкой выплат полезно открыть «Инспекторы» и проверить, не менялись ли реквизиты.</p></div></header>
      <section className="card">
        <div className="toolbar">
          <select value={table} onChange={(e) => setTable(e.target.value)} aria-label="Раздел">
            {Object.entries(TABLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="muted">{loading ? "Загрузка…" : `${data?.length ?? 0} записей`}</span>
        </div>
        <ErrorLine error={error} />
        <div className="table-wrap">
          <table>
            <thead><tr><th>Когда</th><th>Кто</th><th>Раздел</th><th>Запись</th><th>Действие</th><th>Изменения</th></tr></thead>
            <tbody>
              {(data ?? []).map((a) => (
                <tr key={a.id}>
                  <td className="nowrap">{new Date(a.at).toLocaleString("ru-RU")}</td><td>{a.user ?? "система"}</td><td>{TABLES[a.table_name] ?? a.table_name}</td>
                  <td>#{a.record_id ?? "—"}</td><td>{{ insert: "создано", update: "изменено", delete: "удалено" }[a.action as string] ?? a.action}</td>
                  <td className="wrap small">{Object.entries(a.changes).map(([k, v]: any) => `${k}: ${Array.isArray(v) ? `${v[0] ?? "—"} → ${v[1] ?? "—"}` : v}`).join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
