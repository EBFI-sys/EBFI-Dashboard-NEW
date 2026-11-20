import { useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadCsv, monthLabel, num, pct, thisMonth } from "../api";
import { useAuth } from "../auth";
import DataTable, { Col } from "../components/DataTable";
import { ErrorLine, Pill, Toast, useAsync } from "../components/ui";
import { CurrencySwitch, useCurrency } from "../currency";

const MONEY = ["base_inr", "gst_inr", "tds_inr", "wht_inr", "cash_in_inr", "admin_inr", "cost_inr", "rko_inr", "net_inr"] as const;
const OPTIONAL_MONEY = new Set(["gst_inr", "tds_inr", "wht_inr", "cash_in_inr", "admin_inr", "rko_inr"]);
const LABEL: Record<string, string> = {
  base_inr: "Выручка", gst_inr: "GST", tds_inr: "TDS", wht_inr: "WHT", cash_in_inr: "Приход", admin_inr: "Админка", cost_inr: "Подряд", rko_inr: "РКО", net_inr: "Прибыль",
};

export default function Pnl() {
  const { can } = useAuth();
  const { cur, conv, fmt, missing } = useCurrency();
  const [month, setMonth] = useState(thisMonth());
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(`/lines?month=${month}`), [month]);
  const months = useAsync(() => api.get<any[]>("/months"), []);
  const [toast, setToast] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sure, setSure] = useState(false);
  const [visible, setVisible] = useState<any[]>([]);
  const rows = data ?? [];
  const closed = (months.data ?? []).find((m) => m.month === month);
  const sum = (rs: any[], k: string) => rs.reduce((a, r) => a + (r.calc[k] ?? 0), 0);
  const provisional = rows.some((r) => r.calc.fx_provisional && r.currency !== "INR");
  const f = (inr: number | null | undefined) => fmt(inr, month);

  const close = async () => {
    setErr(null);
    try {
      const r = await api.post(`/months/${month}/close`);
      setToast(`Месяц закрыт, зафиксировано строк: ${r.lines_frozen}`);
      setSure(false);
      months.reload();
      reload();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const cols: Col[] = [
    { key: "job_number", label: "Job №", cls: "mono", render: (r) => <Link to={`/jobs/${r.job_id}`}>{r.job_number}</Link> },
    { key: "client_name", label: "Клиент" },
    { key: "country", label: "Страна", optional: true },
    { key: "inspector_name", label: "Инспектор" },
    { key: "owner", label: "Чья" },
    { key: "job_status", label: "Статус", render: (r) => <Pill status={r.job_status} /> },
    { key: "quantity", label: "Кол-во", align: "r", total: (rs) => `${num(sum(rs, "man_days"), 1)} MD`, render: (r) => num(r.quantity, 2).replace(/\.00$/, "") },
    { key: "client_rate", label: "Ставка", align: "r", optional: true, text: (r) => `${r.client_rate} ${r.currency}`, sortNumeric: false,
      render: (r) => `${num(r.client_rate, 2).replace(/\.00$/, "")} ${r.currency}` },
    { key: "fx", label: "Курс", align: "r", optional: true, text: (r) => r.calc.fx, render: (r) => (r.currency === "INR" ? "—" : num(r.calc.fx, 2)) },
    ...MONEY.map((k): Col => ({
      key: k, label: LABEL[k], align: "r", text: (r) => r.calc[k], optional: OPTIONAL_MONEY.has(k), total: (rs) => f(sum(rs, k)),
      render: (r) => k === "net_inr" ? <b className={(r.calc[k] ?? 0) < 0 ? "neg" : ""}>{f(r.calc[k])}</b> : f(r.calc[k]),
    })),
    { key: "margin", label: "Маржа", align: "r", text: (r) => r.calc.margin, render: (r) => pct(r.calc.margin),
      total: (rs) => pct(sum(rs, "base_inr") ? (sum(rs, "net_inr") / sum(rs, "base_inr")) * 100 : null) },
  ];

  const csv = () => downloadCsv(`fin-results-${month}-${cur}.csv`, visible.map((r) => ({
    job: r.job_number, client: r.client_name, country: r.country, inspector: r.inspector_name, owner: r.owner, status: r.job_status,
    dates: r.dates_text, qty: r.quantity, unit: r.unit, currency: r.currency, rate: r.client_rate, cost_rate: r.inspector_rate, fx: r.calc.fx,
    ...Object.fromEntries(MONEY.map((k) => [k, conv(r.calc[k], month)?.toFixed(2)])),
  })), [
    { key: "job", label: "Job number" }, { key: "client", label: "Client" }, { key: "country", label: "Country" }, { key: "inspector", label: "Inspector" },
    { key: "owner", label: "Чья" }, { key: "status", label: "Статус" }, { key: "dates", label: "Даты" }, { key: "qty", label: "Total" }, { key: "unit", label: "Ед." },
    { key: "currency", label: "Валюта" }, { key: "rate", label: "Manday Rate" }, { key: "cost_rate", label: "Мы платим" }, { key: "fx", label: "Курс" },
    ...MONEY.map((k) => ({ key: k, label: `${LABEL[k]}, ${cur}` })),
  ]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Финансовые результаты за {monthLabel(month)}</h1>
          <p className="lede">Выручка <b>{f(sum(visible, "base_inr"))}</b>, чистая прибыль <b>{f(sum(visible, "net_inr"))}</b>, приход на счёт <b>{f(sum(visible, "cash_in_inr"))}</b>.</p>
        </div>
        <div className="head-actions">
          <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} aria-label="Отчётный месяц" />
          <CurrencySwitch />
          <button className="btn ghost" onClick={csv}>Excel (CSV)</button>
          {closed ? <span className="pill ok">Закрыт {closed.closed_by}</span> : can("close_month") && (
            sure ? <><button className="btn danger" onClick={close}>Закрыть {monthLabel(month)}</button><button className="btn ghost" onClick={() => setSure(false)}>Отмена</button></>
              : <button className="btn" onClick={() => setSure(true)}>Закрыть месяц</button>
          )}
        </div>
      </header>
      {sure && <div className="banner soft">После закрытия курс и ставки налогов фиксируются, строки месяца нельзя менять. Перед закрытием внесите курс RBI на последний день месяца в «Справочники → Курсы».</div>}
      {provisional && !closed && <div className="banner soft">Курс за этот месяц ещё не внесён — цифры посчитаны по курсу прошлого месяца.</div>}
      {missing(month) && <div className="banner soft">Нет курса {cur} к INR за этот месяц — суммы в {cur} не показаны. Внесите курс в «Справочники → Курсы».</div>}
      <ErrorLine error={err || error} />
      <section className="card">
        <DataTable rows={rows} cols={cols} onVisible={setVisible}
          empty={loading ? "Загрузка…" : "За этот месяц строк нет. Строки добавляются в карточке работы в Табеле."}
          storageKey="pnl" footLabel={(rs) => `Итого, ${rs.length} строк`} />
      </section>
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
