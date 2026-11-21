import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money, monthLabel, num, today } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { InvoiceFile } from "../components/Files";
import { Modal, Pill } from "../components/ui";
import { CURRENCIES } from "../refs";

/** The inspector's jobs from the Табель with what is due to him, to tick the ones this invoice covers. */
function WorkPicker({ value, onChange, row, patch }: { value: number[]; onChange: (v: number[]) => void; row: any; patch: (d: Record<string, unknown>) => void }) {
  const [work, setWork] = useState<any[] | null>(null);
  useEffect(() => {
    setWork(null);
    if (row.inspector_id) api.get<any[]>(`/inspectors/${row.inspector_id}/work${row.id ? `?invoice_id=${row.id}` : ""}`).then(setWork).catch(() => setWork([]));
  }, [row.inspector_id, row.id]);
  if (!row.inspector_id) return <p className="muted small">Сначала выберите инспектора — здесь появятся его работы из Табеля.</p>;
  if (!work) return <p className="muted small">Загрузка работ…</p>;
  if (!work.length) return <p className="muted small">В Табеле нет работ этого инспектора.</p>;
  const sel = new Set<number>(value ?? []);
  const chosen = work.filter((w) => sel.has(w.job_id));
  const totals: Record<string, number> = {};
  for (const w of chosen) for (const [c, v] of Object.entries<number>(w.amounts)) totals[c] = (totals[c] ?? 0) + v;
  const days = chosen.reduce((a, w) => a + w.days, 0);
  const one = Object.keys(totals).length === 1 ? Object.keys(totals)[0] : null;
  return (
    <div>
      <div className="work-pick">
        <table>
          <thead><tr><th /><th>Job №</th><th>Клиент</th><th>Даты</th><th className="r">Дней</th><th className="r">Ставка</th><th className="r">К оплате</th><th>Счёт</th></tr></thead>
          <tbody>
            {work.map((w) => (
              <tr key={w.job_id} className={w.invoiced_in ? "done" : ""}>
                <td><input type="checkbox" checked={sel.has(w.job_id)} aria-label={w.job_number}
                  onChange={() => { const n = new Set(sel); n.has(w.job_id) ? n.delete(w.job_id) : n.add(w.job_id); onChange([...n]); }} /></td>
                <td className="mono">{w.job_number}</td>
                <td>{w.client}</td>
                <td className="small">{w.dates || w.months.map(monthLabel).join(", ")}</td>
                <td className="r">{num(w.days, 1)}</td>
                <td className="r">{w.rates.join(" / ")}</td>
                <td className="r">{Object.entries<number>(w.amounts).map(([c, v]) => money(v, c)).join(" + ")}</td>
                <td className="small">{w.invoiced_in ? `уже в счёте ${w.invoiced_in}` : "не выставлен"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="sum-line" style={{ marginTop: 8 }}>
        <span>Выбрано работ: <b>{chosen.length}</b></span>
        <span>Дней: <b>{num(days, 1)}</b></span>
        <span>По Табелю: <b>{Object.entries(totals).map(([c, v]) => money(v, c)).join(" + ") || "—"}</b></span>
        {one && <button type="button" className="btn small ghost" onClick={() => patch({ amount: totals[one], currency: one, days,
          dates_text: chosen.map((w) => w.dates).filter(Boolean).join("; ") || row.dates_text })}>Подставить в счёт</button>}
      </div>
    </div>
  );
}

function CheckModal({ inv, onClose }: { inv: any; onClose: () => void }) {
  const c = inv.check;
  return (
    <Modal title={`Сверка счёта ${inv.number ?? ""} · ${inv.inspector_name}`} onClose={onClose} wide>
      {c.status === "no_jobs" && <p>К счёту не привязаны работы. Откройте счёт («карандаш») и отметьте работы инспектора из Табеля.</p>}
      {c.status === "no_lines" && <p>{c.message}. Проверьте инспектора в карточках работ или привязку работ к счёту.</p>}
      {c.problems?.length > 0 && <ul className="problems">{c.problems.map((p: string) => <li key={p}>{p}</li>)}</ul>}
      {c.rows?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Job №</th><th>Месяц</th><th>Даты</th><th className="r">Кол-во</th><th className="r">Ставка</th><th className="r">OT</th><th className="r">Сумма по Табелю</th><th /></tr></thead>
            <tbody>
              {c.rows.map((r: any, i: number) => (
                <tr key={i} className={r.currency !== inv.currency || !r.rate ? "hl" : ""}>
                  <td className="mono">{r.job_number}</td><td>{monthLabel(r.month)}</td><td className="small">{r.dates_text ?? "—"}</td>
                  <td className="r">{num(r.quantity, 2).replace(/\.00$/, "")}</td><td className="r">{money(r.rate, r.currency)}</td>
                  <td className="r">{r.overtime ? money(r.overtime, r.currency) : "—"}</td><td className="r">{money(r.amount, r.currency)}</td>
                  <td><Link className="btn small ghost" to={`/jobs/${r.job_id}`}>Открыть работу →</Link></td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td colSpan={6}>Итого по Табелю</td><td className="r">{Object.entries<number>(c.by_currency ?? {}).map(([k, v]) => money(v, k)).join(" + ")}</td><td /></tr>
              <tr><td colSpan={6}>Сумма счёта</td><td className="r">{money(inv.amount, inv.currency)}</td><td /></tr></tfoot>
          </table>
        </div>
      )}
      <p className="muted small">Подсвечены строки с нулевой ставкой или в другой валюте. Если ошибка в Табеле — исправьте ставку или даты в работе; если в счёте — исправьте счёт.</p>
    </Modal>
  );
}

export default function Payouts() {
  const [show, setShow] = useState<"open" | "all">("open");
  const [check, setCheck] = useState<any | null>(null);

  const fields: Field[] = [
    { key: "inspector_id", label: "Инспектор", type: "ref", ref: "inspectors", required: true },
    { key: "number", label: "Номер счёта" },
    { key: "invoice_date", label: "Дата счёта", type: "date" },
    { key: "job_ids", label: "Работы инспектора из Табеля", list: false, wide: true,
      input: ({ value, onChange, row, patch }) => <WorkPicker value={value} onChange={onChange} row={row} patch={patch} /> },
    { key: "job_numbers", label: "EBFI №", form: false, render: (r) => r.job_numbers?.join(", ") || "—", text: (r) => r.job_numbers?.join(", ") },
    { key: "dates_text", label: "Даты", list: false },
    { key: "days", label: "Дней", type: "number" },
    { key: "rate", label: "Ставка", type: "money", currencyKey: "currency", list: false },
    { key: "amount", label: "Сумма", type: "money", currencyKey: "currency", required: true, text: (r) => r.amount,
      render: (r) => {
        const st = r.check?.status;
        const bad = st && st !== "ok";
        const label = { amount: "≠ Табелю", currency: "другая валюта", no_jobs: "нет работ", no_lines: "нет в Табеле" }[st as string];
        return (
          <span className="nowrap">
            {money(r.amount, r.currency)}
            {bad && <button type="button" className="check-btn bad" title="Показать, в чём расхождение"
              onClick={(e) => { e.stopPropagation(); setCheck(r); }}>{label} ›</button>}
          </span>
        );
      } },
    { key: "currency", label: "Валюта", type: "select", options: CURRENCIES, required: true },
    { key: "payment_method_id", label: "Способ оплаты", type: "ref", ref: "payment-methods" },
    { key: "paid", label: "Оплачено", type: "bool", render: (r) => <Pill status={r.paid ? "Оплачено" : "К оплате"} />, text: (r) => (r.paid ? "Оплачено" : "К оплате") },
    { key: "paid_date", label: "Дата оплаты", type: "date" },
    { key: "comment", label: "Комментарий", type: "textarea", list: false },
  ];

  return (
    <div className="page">
      <header className="page-head"><div><h1>Реестр входящих счетов</h1>
        <p className="lede">Счета, которые присылает инспектор: регистрация, PDF и отметка оплаты. Пометка у суммы — расхождение с Табелем (дни × ставка инспектора в его валюте); нажмите на неё, чтобы увидеть, где именно.</p></div></header>
      <CrudTable periodKey="invoice_date" endpoint="/inspector-invoices" title={show === "open" ? "К оплате" : "Все счета"} fields={fields} csvName="inspector-invoices.csv"
        defaults={{ currency: "USD", paid: false, invoice_date: today(), job_ids: [] }}
        filter={(r) => show === "all" || !r.paid}
        toolbar={() => (
          <div className="seg">
            <button className={show === "open" ? "on" : ""} onClick={() => setShow("open")}>К оплате</button>
            <button className={show === "all" ? "on" : ""} onClick={() => setShow("all")}>Все</button>
          </div>
        )}
        rowActions={(r, reload) => <InvoiceFile url={r.sp_file_url} hasFile={r.has_file} uploadUrl={`/api/inspector-invoices/${r.id}/file`} reload={reload} />} />
      {check && <CheckModal inv={check} onClose={() => setCheck(null)} />}
    </div>
  );
}

