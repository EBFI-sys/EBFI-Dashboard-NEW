import { useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadCsv, inr, monthLabel, num, pct, thisMonth } from "../api";
import { useAuth } from "../auth";
import { ErrorLine, Pill, Toast, useAsync } from "../components/ui";

export default function Pnl() {
  const { can } = useAuth();
  const [month, setMonth] = useState(thisMonth());
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(`/lines?month=${month}`), [month]);
  const months = useAsync(() => api.get<any[]>("/months"), []);
  const [toast, setToast] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sure, setSure] = useState(false);
  const rows = data ?? [];
  const closed = (months.data ?? []).find((m) => m.month === month);
  const sum = (k: string) => rows.reduce((a, r) => a + (r.calc[k] ?? 0), 0);
  const provisional = rows.some((r) => r.calc.fx_provisional && r.currency !== "INR");

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

  const csv = () => downloadCsv(`pnl-${month}.csv`, rows.map((r) => ({
    job: r.job_number, client: r.client_name, country: r.country, inspector: r.inspector_name, owner: r.owner, status: r.job_status,
    dates: r.dates_text, qty: r.quantity, unit: r.unit, currency: r.currency, rate: r.client_rate, cost_rate: r.inspector_rate,
    fx: r.calc.fx, base: r.calc.base_inr, gst: r.calc.gst_inr, tds: r.calc.tds_inr, cash: r.calc.cash_in_inr, admin: r.calc.admin_inr,
    cost: r.calc.cost_inr, rko: r.calc.rko_inr, net: r.calc.net_inr,
  })), [
    { key: "job", label: "Job number" }, { key: "client", label: "Client" }, { key: "country", label: "Country" }, { key: "inspector", label: "Inspector" },
    { key: "owner", label: "Чья" }, { key: "status", label: "Статус" }, { key: "dates", label: "Даты" }, { key: "qty", label: "Total" }, { key: "unit", label: "Ед." },
    { key: "currency", label: "Валюта" }, { key: "rate", label: "Manday Rate" }, { key: "cost_rate", label: "Мы платим" }, { key: "fx", label: "Курс" },
    { key: "base", label: "Выручка B, INR" }, { key: "gst", label: "GST" }, { key: "tds", label: "TDS" }, { key: "cash", label: "Приход на р/с" },
    { key: "admin", label: "Админка" }, { key: "cost", label: "Подряд" }, { key: "rko", label: "РКО" }, { key: "net", label: "Чистая прибыль" },
  ]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>P&amp;L за {monthLabel(month)}</h1>
          <p className="lede">Выручка <b>{inr(sum("base_inr"))}</b>, чистая прибыль <b>{inr(sum("net_inr"))}</b>, приход на счёт <b>{inr(sum("cash_in_inr"))}</b>.</p>
        </div>
        <div className="head-actions">
          <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} aria-label="Месяц" />
          <button className="btn ghost" onClick={csv}>Excel (CSV)</button>
          {closed ? <span className="pill ok">Закрыт {closed.closed_by}</span> : can("close_month") && (
            sure ? <><button className="btn danger" onClick={close}>Закрыть {monthLabel(month)}</button><button className="btn ghost" onClick={() => setSure(false)}>Отмена</button></>
              : <button className="btn" onClick={() => setSure(true)}>Закрыть месяц</button>
          )}
        </div>
      </header>
      {sure && <div className="banner soft">После закрытия курс и ставки налогов фиксируются, строки месяца нельзя менять. Перед закрытием внесите курс RBI на последний день месяца в «Справочники → Курсы».</div>}
      {provisional && !closed && <div className="banner soft">Курс за этот месяц ещё не внесён — цифры посчитаны по курсу прошлого месяца.</div>}
      <ErrorLine error={err || error} />
      <section className="card">
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>Job №</th><th>Клиент</th><th>Страна</th><th>Инспектор</th><th>Чья</th><th>Статус</th><th className="r">Кол-во</th><th className="r">Ставка</th>
              <th className="r">Курс</th><th className="r">Выручка</th><th className="r">GST</th><th className="r">TDS</th><th className="r">Приход</th>
              <th className="r">Админка</th><th className="r">Подряд</th><th className="r">РКО</th><th className="r">Прибыль</th><th className="r">Маржа</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono"><Link to={`/jobs/${r.job_id}`}>{r.job_number}</Link></td><td>{r.client_name}</td><td>{r.country ?? "—"}</td>
                  <td>{r.inspector_name ?? "—"}</td><td>{r.owner ?? "—"}</td><td><Pill status={r.job_status} /></td>
                  <td className="r">{num(r.quantity, 2).replace(/\.00$/, "")}</td><td className="r">{num(r.client_rate, 2).replace(/\.00$/, "")} {r.currency}</td>
                  <td className="r">{r.currency === "INR" ? "—" : num(r.calc.fx, 2)}</td>
                  <td className="r">{inr(r.calc.base_inr)}</td><td className="r">{inr(r.calc.gst_inr)}</td><td className="r">{inr(r.calc.tds_inr)}</td>
                  <td className="r">{inr(r.calc.cash_in_inr)}</td><td className="r">{inr(r.calc.admin_inr)}</td><td className="r">{inr(r.calc.cost_inr)}</td>
                  <td className="r">{inr(r.calc.rko_inr)}</td><td className={"r " + ((r.calc.net_inr ?? 0) < 0 ? "neg" : "")}><b>{inr(r.calc.net_inr)}</b></td>
                  <td className="r">{pct(r.calc.margin)}</td>
                </tr>
              ))}
              {!loading && rows.length === 0 && <tr><td colSpan={18} className="empty">За этот месяц строк нет. Строки добавляются в карточке работы.</td></tr>}
            </tbody>
            {rows.length > 0 && (
              <tfoot><tr>
                <td colSpan={9}>Итого, {rows.length} строк · {num(sum("man_days"), 1)} MD</td>
                {["base_inr", "gst_inr", "tds_inr", "cash_in_inr", "admin_inr", "cost_inr", "rko_inr", "net_inr"].map((k) => <td key={k} className="r">{inr(sum(k))}</td>)}
                <td className="r">{pct(sum("base_inr") ? (sum("net_inr") / sum("base_inr")) * 100 : null)}</td>
              </tr></tfoot>
            )}
          </table>
        </div>
      </section>
      <Toast text={toast} onDone={() => setToast(null)} />
    </div>
  );
}
