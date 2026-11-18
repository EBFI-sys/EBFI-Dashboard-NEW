import { useMemo, useState } from "react";
import { api, dateLabel, downloadCsv, money, monthLabel, num } from "../api";
import { useAuth } from "../auth";
import { invalidateRef, useRef_ } from "../refs";
import { DatesField } from "./Calendar";
import { ErrorLine, Modal, Pill, Toast, useAsync } from "./ui";

export type Field = {
  key: string;
  label: string;
  type?: "text" | "number" | "money" | "date" | "select" | "bool" | "textarea" | "ref" | "multiref" | "status" | "dates";
  monthKey?: string; // dates field: which field holds the line month
  options?: string[];
  ref?: string; // reference list endpoint, e.g. "clients"
  refLabel?: string;
  list?: boolean; // show as a column (default true)
  form?: boolean; // show in the form (default true)
  required?: boolean;
  currencyKey?: string; // money column: which field holds the currency
  render?: (row: any) => React.ReactNode;
  wide?: boolean;
  hint?: string;
};

type Props = {
  endpoint: string;
  title: string;
  fields: Field[];
  query?: string;
  defaults?: Record<string, unknown>;
  refName?: string; // invalidate this cached reference list after changes
  rowActions?: (row: any, reload: () => void) => React.ReactNode;
  toolbar?: (rows: any[], reload: () => void) => React.ReactNode;
  writeRight?: string;
  filter?: (row: any) => boolean;
  csvName?: string;
  onRowClick?: (row: any) => void;
  allowCreate?: boolean;
  periodKey?: string; // date field to filter by period (month or custom range)
};

/** Indian financial year quarter: 2026-11-15 -> "Q3 FY27". */
export function quarterOf(d: string) {
  const y = Number(d.slice(0, 4)), m = Number(d.slice(5, 7));
  const fy = m >= 4 ? y + 1 : y;
  return `Q${Math.floor(((m - 4 + 12) % 12) / 3) + 1} FY${String(fy).slice(2)}`;
}

function RefSelect({ f, value, onChange }: { f: Field; value: any; onChange: (v: any) => void }) {
  const rows = useRef_(f.ref!);
  const label = f.refLabel ?? "name";
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}>
      <option value="">—</option>
      {rows.filter((r) => !r.deleted).map((r) => (
        <option key={r.id} value={r.id}>{r[label]}</option>
      ))}
    </select>
  );
}

function MultiRef({ f, value, onChange }: { f: Field; value: number[]; onChange: (v: number[]) => void }) {
  const rows = useRef_(f.ref!);
  const [q, setQ] = useState("");
  const label = f.refLabel ?? "name";
  const sel = new Set(value ?? []);
  const shown = rows.filter((r) => sel.has(r.id) || (q && String(r[label]).toLowerCase().includes(q.toLowerCase()))).slice(0, 30);
  return (
    <div className="multiref">
      <input placeholder="Найти…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="multiref-list">
        {shown.map((r) => (
          <label key={r.id} className="check">
            <input type="checkbox" checked={sel.has(r.id)} onChange={(e) => {
              const n = new Set(sel);
              e.target.checked ? n.add(r.id) : n.delete(r.id);
              onChange([...n]);
            }} />
            {r[label]}
          </label>
        ))}
      </div>
    </div>
  );
}

export function FieldInput({ f, value, onChange, row }: { f: Field; value: any; onChange: (v: any) => void; row?: any }) {
  switch (f.type) {
    case "dates":
      return <DatesField value={value} onChange={onChange} month={f.monthKey ? row?.[f.monthKey] : undefined} />;
    case "number":
    case "money":
      return <input type="number" step="any" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)} />;
    case "date":
      return <input type="date" value={(value ?? "").slice(0, 10)} onChange={(e) => onChange(e.target.value || null)} />;
    case "select":
    case "status":
      return (
        <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
          {!f.required && <option value="">—</option>}
          {f.options!.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    case "bool":
      return <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />;
    case "textarea":
      return <textarea rows={3} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
    case "ref":
      return <RefSelect f={f} value={value} onChange={onChange} />;
    case "multiref":
      return <MultiRef f={f} value={value} onChange={onChange} />;
    default:
      return <input value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
  }
}

function RefLabel({ f, id }: { f: Field; id: any }) {
  const rows = useRef_(f.ref!);
  const r = rows.find((x) => x.id === id);
  return <>{r ? r[f.refLabel ?? "name"] : id == null ? "—" : `#${id}`}</>;
}

export function cell(f: Field, row: any): React.ReactNode {
  if (f.render) return f.render(row);
  const v = row[f.key];
  switch (f.type) {
    case "money":
      return money(v, f.currencyKey ? row[f.currencyKey] : "INR");
    case "number":
      return num(v, 2).replace(/\.00$/, "");
    case "date":
      return dateLabel(v);
    case "bool":
      return v ? "да" : "—";
    case "status":
      return <Pill status={v} />;
    case "ref":
      return <RefLabel f={f} id={v} />;
    default:
      return v ?? "—";
  }
}

export function EditForm({ fields, initial, onSave, onCancel, title }: {
  fields: Field[]; initial: any; onSave: (d: any) => Promise<void>; onCancel: () => void; title: string;
}) {
  const [data, setData] = useState<any>({ ...initial });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    for (const f of fields) {
      if (f.required && (data[f.key] == null || data[f.key] === "")) {
        setErr(`Заполните поле «${f.label}»`);
        return;
      }
    }
    setBusy(true);
    try {
      await onSave(data);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onCancel} wide={fields.filter((f) => f.form !== false).length > 8}>
      <form onSubmit={submit} className="form-grid">
        {fields.filter((f) => f.form !== false).map((f) => (
          <label key={f.key} className={"field" + (f.wide || f.type === "textarea" || f.type === "multiref" || f.type === "dates" ? " wide" : "") + (f.type === "bool" ? " inline" : "")}>
            <span>{f.label}{f.required && " *"}</span>
            <FieldInput f={f} value={data[f.key]} row={data} onChange={(v) => setData((d: any) => ({ ...d, [f.key]: v }))} />
            {f.hint && <small>{f.hint}</small>}
          </label>
        ))}
        <ErrorLine error={err} />
        <div className="form-actions wide">
          <button type="button" className="btn ghost" onClick={onCancel}>Отмена</button>
          <button type="submit" className="btn primary" disabled={busy}>{busy ? "Сохраняю…" : "Сохранить"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function CrudTable(p: Props) {
  const { can } = useAuth();
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(p.endpoint + (p.query ? `?${p.query}` : "")), [p.endpoint, p.query]);
  const [edit, setEdit] = useState<any | null>(null);
  const [q, setQ] = useState("");
  const [period, setPeriod] = useState<string>("all");
  const [range, setRange] = useState<{ from: string; to: string }>({ from: "", to: "" });
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const canWrite = can(p.writeRight ?? "write");
  const cols = p.fields.filter((f) => f.list !== false);

  const rows = useMemo(() => {
    let r = (data ?? []).filter((x) => (p.filter ? p.filter(x) : true));
    if (p.periodKey && period !== "all") {
      const k = p.periodKey;
      r = r.filter((x) => {
        const d: string = (x[k] ?? "").slice(0, 10);
        if (!d) return false;
        if (period === "range") return (!range.from || d >= range.from) && (!range.to || d <= range.to);
        if (period.startsWith("Q")) return quarterOf(d) === period;
        return d.slice(0, 7) === period;
      });
    }
    if (q) {
      const s = q.toLowerCase();
      r = r.filter((x) => Object.values(x).some((v) => v != null && String(v).toLowerCase().includes(s)));
    }
    if (sort) r = [...r].sort((a, b) => (a[sort.key] ?? "") > (b[sort.key] ?? "") ? sort.dir : -sort.dir);
    return r;
  }, [data, q, sort, p.filter, p.periodKey, period, range]);

  const periods = useMemo(() => {
    if (!p.periodKey) return { months: [] as string[], quarters: [] as string[] };
    const ds = (data ?? []).map((x) => (x[p.periodKey!] ?? "").slice(0, 10)).filter(Boolean);
    return {
      months: [...new Set(ds.map((d) => d.slice(0, 7)))].sort().reverse(),
      quarters: [...new Set(ds.map(quarterOf))].sort().reverse(),
    };
  }, [data, p.periodKey]);

  const save = async (d: any) => {
    if (d.id) await api.patch(`${p.endpoint}/${d.id}`, d);
    else await api.post(p.endpoint, d);
    if (p.refName) invalidateRef(p.refName);
    setEdit(null);
    setToast("Сохранено");
    reload();
  };
  const remove = async (row: any) => {
    // confirmation happens in DeleteBar
    await api.del(`${p.endpoint}/${row.id}`);
    if (p.refName) invalidateRef(p.refName);
    setEdit(null);
    setToast("Удалено");
    reload();
  };

  return (
    <section className="card">
      <div className="toolbar">
        <h2>{p.title}</h2>
        <span className="muted">{loading ? "Загрузка…" : `${rows.length} записей`}</span>
        <div className="spacer" />
        {p.periodKey && (
          <>
            <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Период">
              <option value="all">Весь период</option>
              {periods.months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
              {periods.quarters.map((qq) => <option key={qq} value={qq}>{qq.replace("Q", "Квартал ")}</option>)}
              <option value="range">Свой период…</option>
            </select>
            {period === "range" && (
              <span className="range">
                <input type="date" aria-label="С" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} />
                <span>—</span>
                <input type="date" aria-label="По" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} />
              </span>
            )}
          </>
        )}
        <input className="search" placeholder="Поиск" value={q} onChange={(e) => setQ(e.target.value)} />
        {p.toolbar?.(rows, reload)}
        <button className="btn ghost" onClick={() => downloadCsv(p.csvName ?? "export.csv", rows, cols.map((c) => ({ key: c.key, label: c.label })))}>CSV</button>
        {canWrite && p.allowCreate !== false && <button className="btn primary" onClick={() => setEdit({ ...(p.defaults ?? {}) })}>Добавить</button>}
      </div>
      <ErrorLine error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} className={c.type === "money" || c.type === "number" ? "r" : ""}
                    onClick={() => setSort({ key: c.key, dir: sort?.key === c.key ? (-sort.dir as 1 | -1) : 1 })}>
                  {c.label}{sort?.key === c.key ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={p.onRowClick ? "clickable" : ""} onClick={() => p.onRowClick?.(r)}>
                {cols.map((c) => (
                  <td key={c.key} className={c.type === "money" || c.type === "number" ? "r" : c.type === "textarea" ? "wrap" : ""}>{cell(c, r)}</td>
                ))}
                <td className="actions" onClick={(e) => e.stopPropagation()}>
                  {p.rowActions?.(r, reload)}
                  {canWrite && <button className="btn small ghost" onClick={() => setEdit(r)}>Изменить</button>}
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={cols.length + 1} className="empty">{p.allowCreate === false ? "Пока пусто." : "Пока пусто. Нажмите «Добавить», чтобы создать первую запись."}</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {edit && (
        <>
          <EditForm title={edit.id ? "Изменить" : "Новая запись"} fields={p.fields} initial={edit} onSave={save} onCancel={() => setEdit(null)} />
          {edit.id && can("delete") && <DeleteBar onDelete={() => remove(edit)} />}
        </>
      )}
      <Toast text={toast} onDone={() => setToast(null)} />
    </section>
  );
}

function DeleteBar({ onDelete }: { onDelete: () => Promise<void> }) {
  const [sure, setSure] = useState(false);
  return (
    <div className="delete-bar">
      {sure ? (
        <>
          <span>Запись будет скрыта (останется в журнале).</span>
          <button className="btn danger small" onClick={onDelete}>Да, удалить</button>
          <button className="btn ghost small" onClick={() => setSure(false)}>Отмена</button>
        </>
      ) : (
        <button className="btn ghost small" onClick={() => setSure(true)}>Удалить запись</button>
      )}
    </div>
  );
}
