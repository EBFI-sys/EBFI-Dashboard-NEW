import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, monthLabel } from "../api";
import { Modal, Pill, useAsync } from "./ui";

const WEEK = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const pad = (n: number) => String(n).padStart(2, "0");
const iso = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;

export function shiftMonth(month: string, by: number) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
}

/** Month grid, Monday first. `render` fills a day cell; `onPick` makes days clickable. */
export function MonthGrid({ month, render, onPick, selected, today = new Date().toISOString().slice(0, 10) }: {
  month: string; render?: (date: string) => React.ReactNode; onPick?: (date: string) => void; selected?: Set<string>; today?: string;
}) {
  const [y, m] = month.split("-").map(Number);
  const first = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells: (string | null)[] = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => iso(y, m, i + 1))];
  while (cells.length % 7) cells.push(null);
  return (
    <div className="cal">
      {WEEK.map((w) => <div key={w} className="cal-head">{w}</div>)}
      {cells.map((d, i) => d ? (
        <button key={d} type="button" className={"cal-day" + (selected?.has(d) ? " on" : "") + (d === today ? " today" : "") + (i % 7 >= 5 ? " weekend" : "")}
          onClick={() => onPick?.(d)} disabled={!onPick} aria-pressed={selected?.has(d)}>
          <span className="cal-num">{Number(d.slice(8))}</span>
          {render?.(d)}
        </button>
      ) : <div key={"x" + i} className="cal-empty" />)}
    </div>
  );
}

/** Pop-up calendar of agreed inspection dates for all jobs. */
export function JobsCalendar({ onClose }: { onClose: () => void }) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [day, setDay] = useState<string | null>(null);
  const { data, loading } = useAsync(() => api.get<any[]>(`/calendar?month=${month}`), [month]);
  const byDay = useMemo(() => {
    const m = new Map<string, any[]>();
    for (const e of data ?? []) m.set(e.date, [...(m.get(e.date) ?? []), e]);
    return m;
  }, [data]);
  const list = day ? byDay.get(day) ?? [] : [];
  const busiest = Math.max(1, ...[...byDay.values()].map((v) => v.length));

  return (
    <Modal title="Календарь согласованных дат" onClose={onClose} wide>
      <div className="cal-nav">
        <button className="btn small ghost" onClick={() => { setMonth(shiftMonth(month, -1)); setDay(null); }} aria-label="Предыдущий месяц">←</button>
        <strong>{monthLabel(month)}</strong>
        <button className="btn small ghost" onClick={() => { setMonth(shiftMonth(month, 1)); setDay(null); }} aria-label="Следующий месяц">→</button>
        <span className="muted">{loading ? "Загрузка…" : `${data?.length ?? 0} инспекторо-дней, ${new Set((data ?? []).map((e) => e.job_id)).size} работ`}</span>
      </div>
      <MonthGrid month={month} selected={day ? new Set([day]) : undefined} onPick={(d) => setDay(d === day ? null : d)}
        render={(d) => {
          const n = byDay.get(d)?.length ?? 0;
          return n ? <span className="cal-mark" style={{ opacity: 0.35 + (0.65 * n) / busiest }}>{n}</span> : null;
        }} />
      <p className="muted small">Число в дне — сколько инспекторов работает. Нажмите на день, чтобы увидеть работы.</p>
      {day && (
        <div className="table-wrap">
          <h3>{Number(day.slice(8))} {monthLabel(month)}</h3>
          <table>
            <thead><tr><th>Job №</th><th>Клиент</th><th>Инспектор</th><th>Страна</th><th>Чья</th><th>Статус</th></tr></thead>
            <tbody>
              {list.map((e) => (
                <tr key={e.line_id}>
                  <td className="mono"><Link to={`/jobs/${e.job_id}`} onClick={onClose}>{e.job_number}</Link></td>
                  <td>{e.client}</td><td>{e.inspector ?? "—"}</td><td>{e.country ?? "—"}</td><td>{e.owner ?? "—"}</td><td><Pill status={e.status} /></td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={6} className="empty">В этот день инспекций нет.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

/** «Даты работ» field: free text plus a calendar to tick the agreed days. */
export function DatesField({ value, onChange, month }: { value: string | null; onChange: (v: string) => void; month?: string }) {
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [view, setView] = useState(month || new Date().toISOString().slice(0, 7));

  useEffect(() => {
    if (!open) return;
    api.post("/dates/normalize", { text: value ?? "", month: view }).then((r) => {
      setSel(new Set(r.dates));
      if (r.dates.length) setView(r.dates[0].slice(0, 7));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const toggle = async (d: string) => {
    const n = new Set(sel);
    n.has(d) ? n.delete(d) : n.add(d);
    setSel(n);
    const r = await api.post("/dates/normalize", { dates: [...n].sort() });
    onChange(r.text);
  };

  return (
    <div className="dates-field">
      <div className="dates-row">
        <input value={value ?? ""} onChange={(e) => onChange(e.target.value)} placeholder="05,06,07.11.2026" />
        <button type="button" className="btn small" onClick={() => setOpen(!open)}>{open ? "Скрыть" : "Календарь"}</button>
      </div>
      {open && (
        <div className="dates-pop">
          <div className="cal-nav">
            <button type="button" className="btn small ghost" onClick={() => setView(shiftMonth(view, -1))}>←</button>
            <strong>{monthLabel(view)}</strong>
            <button type="button" className="btn small ghost" onClick={() => setView(shiftMonth(view, 1))}>→</button>
            <span className="muted small">Выбрано дней: {sel.size}</span>
          </div>
          <MonthGrid month={view} selected={sel} onPick={toggle} />
        </div>
      )}
    </div>
  );
}
