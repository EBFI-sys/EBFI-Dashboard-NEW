import { Pencil } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, dateLabel, downloadCsv, money, monthLabel, num, thisMonth } from "../api";
import { useAuth } from "../auth";
import { invalidateRef, loadRef, useRef_ } from "../refs";
import { DatesField } from "./Calendar";
import DataTable, { Col } from "./DataTable";
import { ErrorLine, Modal, Pill, Portal, Toast, useAsync, usePersisted } from "./ui";

export type Field = {
  key: string;
  label: string;
  type?: "text" | "number" | "money" | "date" | "select" | "bool" | "textarea" | "ref" | "multiref" | "status" | "dates" | "suggest";
  monthKey?: string; // dates field: which field holds the line month
  options?: string[];
  ref?: string; // reference list endpoint, e.g. "clients"
  refLabel?: string;
  list?: boolean; // show as a column (default true)
  form?: boolean; // show in the form (default true)
  required?: boolean;
  currencyKey?: string; // money column: which field holds the currency
  render?: (row: any) => React.ReactNode;
  text?: (row: any) => string | number | null | undefined; // value for column filters when `render` is used
  wide?: boolean;
  hint?: string;
  optional?: boolean; // column hidden until turned on in «Столбцы»
  mobile?: "head" | "wide" | "hide"; // phone card view
  mlist?: boolean; // shown in the compact phone list
  input?: (p: { value: any; onChange: (v: any) => void; row: any; patch: (d: Record<string, unknown>) => void }) => React.ReactNode;
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
  periodLabel?: string;
  periodDefault?: "current" | "all"; // open on the current month (India time) or on the whole period
  periodKey?: string; // date field to filter by period (month or custom range)
  columnFilters?: boolean; // Excel-style filters in column headers (default true)
  deleteRight?: string; // right needed to delete a record (default "delete": admin only)
  mobileRow?: (row: any, actions: React.ReactNode) => React.ReactNode; // the row in the compact phone list
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

/** Pick several rows of a reference list: chosen ones as removable chips, a search box and a tidy result list. */
function MultiRef({ f, value, onChange }: { f: Field; value: number[]; onChange: (v: number[]) => void }) {
  const rows = useRef_(f.ref!);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const label = f.refLabel ?? "name";
  const sel = value ?? [];
  const has = new Set(sel);
  const byId = new Map(rows.map((r) => [r.id, r]));
  const s = q.trim().toLowerCase();
  const found = s ? rows.filter((r) => !r.deleted && String(r[label]).toLowerCase().includes(s)).slice(0, 40) : [];
  const toggle = (id: number) => {
    onChange(has.has(id) ? sel.filter((x) => x !== id) : [...sel, id]);
  };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, found.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
    if (e.key === "Enter" && found[hi]) { e.preventDefault(); toggle(found[hi].id); setQ(""); setHi(0); }
    if (e.key === "Backspace" && !q && sel.length) onChange(sel.slice(0, -1));
  };
  return (
    <div className="mref">
      <div className="mref-box">
        {sel.map((id) => (
          <span key={id} className="mref-chip">
            {byId.get(id)?.[label] ?? `#${id}`}
            <button type="button" aria-label="Убрать" onClick={() => toggle(id)}>×</button>
          </span>
        ))}
        <input value={q} onChange={(e) => { setQ(e.target.value); setHi(0); }} onKeyDown={key}
          placeholder={sel.length ? "Добавить ещё…" : "Начните вводить имя…"} aria-label={f.label} />
      </div>
      {s && (
        <div className="mref-list" role="listbox">
          {found.length === 0 && <div className="mref-empty">Никого не нашлось</div>}
          {found.map((r, i) => (
            <button type="button" key={r.id} role="option" aria-selected={has.has(r.id)}
              className={"mref-opt" + (i === hi ? " hi" : "") + (has.has(r.id) ? " on" : "")}
              onMouseEnter={() => setHi(i)} onClick={() => toggle(r.id)}>
              <span className="mref-tick">{has.has(r.id) ? "✓" : ""}</span>
              <span className="mref-name">{r[label]}</span>
              {(r.country || r.specialization) && <span className="mref-sub">{[r.country, r.specialization].filter(Boolean).join(" · ")}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function FieldInput({ f, value, onChange, row, patch }: {
  f: Field; value: any; onChange: (v: any) => void; row?: any; patch?: (d: Record<string, unknown>) => void;
}) {
  if (f.input) return <>{f.input({ value, onChange, row, patch: patch ?? (() => undefined) })}</>;
  switch (f.type) {
    case "suggest":
      return <SuggestInput f={f} value={value} onChange={onChange} />;
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

/** Free text with suggestions from a reference list (vendors, countries): type a few letters, pick a match. */
function SuggestInput({ f, value, onChange }: { f: Field; value: any; onChange: (v: any) => void }) {
  const rows = useRef_(f.ref!);
  const id = "dl-" + f.ref + "-" + f.key;
  return (
    <>
      <input list={id} value={value ?? ""} autoComplete="off" onChange={(e) => onChange(e.target.value)} placeholder="Начните вводить…" />
      <datalist id={id}>
        {rows.map((r) => <option key={r.id} value={r[f.refLabel ?? "name"]}>{r.country ?? r.region ?? ""}</option>)}
      </datalist>
    </>
  );
}

/** id -> label maps for every reference list used by the columns (for filters and sorting). */
function useRefMaps(names: string[]) {
  const [maps, setMaps] = useState<Record<string, Map<any, any>>>({});
  const key = names.join(",");
  useEffect(() => {
    let live = true;
    Promise.all(names.map((n) => loadRef(n).then((rows) => [n, rows] as const).catch(() => [n, []] as const))).then((all) => {
      if (!live) return;
      setMaps(Object.fromEntries(all.map(([n, rows]) => [n, new Map(rows.map((r: any) => [r.id, r])) ])));
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return maps;
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
    case "dates": // imported cells may hold "2026-11-20 00:00:00"
      return v ? String(v).replace(/(\d{4})-(\d\d)-(\d\d)(?:[ T]00:00:00)?/g, "$3.$2.$1") : "—";
    default:
      return v ?? "—";
  }
}

function Wrap({ as, children, ...rest }: { as: "div" | "label"; children: React.ReactNode; className?: string }) {
  return as === "div" ? <div {...rest}>{children}</div> : <label {...rest}>{children}</label>;
}

export function EditForm({ fields, initial, onSave, onCancel, title, onFieldChange, onDelete }: {
  fields: Field[]; initial: any; onSave: (d: any) => Promise<void>; onCancel: () => void; title: string;
  onDelete?: () => Promise<void>; // shows «Удалить» in the footer, with a confirmation
  onFieldChange?: (key: string, value: any, data: any) => Promise<Record<string, unknown> | void> | Record<string, unknown> | void;
}) {
  const [data, setData] = useState<any>({ ...initial });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);
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
          <Wrap key={f.key} as={f.input || f.type === "multiref" ? "div" : "label"} className={"field" + (f.wide || f.type === "textarea" || f.type === "multiref" || f.type === "dates" ? " wide" : "") + (f.type === "bool" ? " inline" : "")}>
            <span>{f.label}{f.required && " *"}</span>
            <FieldInput f={f} value={data[f.key]} row={data} patch={(x) => setData((d: any) => ({ ...d, ...x }))}
              onChange={async (v) => {
                setData((d: any) => ({ ...d, [f.key]: v }));
                const extra = await onFieldChange?.(f.key, v, { ...data, [f.key]: v });
                if (extra) setData((d: any) => ({ ...d, ...extra }));
              }} />
            {f.hint && <small>{f.hint}</small>}
          </Wrap>
        ))}
        <ErrorLine error={err} />
        <div className={"form-actions wide" + (onDelete ? " with-delete" : "")}>
          {onDelete && (sure ? (
            <span className="del-confirm">
              <span className="muted small">Скрыть запись? Останется в журнале.</span>
              <button type="button" className="btn danger small" onClick={async () => { try { await onDelete(); } catch (e: any) { setErr(e.message); setSure(false); } }}>Да, удалить</button>
              <button type="button" className="btn ghost small" onClick={() => setSure(false)}>Нет</button>
            </span>
          ) : <button type="button" className="btn ghost danger-text del-btn" onClick={() => setSure(true)}>Удалить</button>)}
          {!sure && <>
            <button type="button" className="btn ghost" onClick={onCancel}>Отмена</button>
            <button type="submit" className="btn primary" disabled={busy}>{busy ? "Сохраняю…" : "Сохранить"}</button>
          </>}
        </div>
      </form>
    </Modal>
  );
}

export default function CrudTable(p: Props) {
  const { can } = useAuth();
  const { data, error, loading, reload } = useAsync(() => api.get<any[]>(p.endpoint + (p.query ? `?${p.query}` : "")), [p.endpoint, p.query]);
  const [edit, setEdit] = useState<any | null>(null);
  // search and period stay while the app is open (leaving the page, opening a record), reset when it is closed
  const [q, setQ] = usePersisted(p.endpoint + ".q", "", "session");
  const [period, setPeriod] = usePersisted<string>(p.endpoint + ".period", p.periodKey && p.periodDefault === "current" ? thisMonth() : "all", "session");
  const [range, setRange] = usePersisted<{ from: string; to: string }>(p.endpoint + ".range", { from: "", to: "" }, "session");
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
    return r;
  }, [data, q, p.filter, p.periodKey, period, range]);
  const [visible, setVisible] = useState<any[]>([]);
  const refMaps = useRefMaps([...new Set(cols.filter((c) => c.type === "ref" && c.ref).map((c) => c.ref!))]);
  const tableCols: Col[] = useMemo(() => cols.map((c) => ({
    key: c.key,
    label: c.label,
    render: (r: any) => cell(c, r),
    align: c.type === "money" || c.type === "number" ? "r" : undefined,
    cls: c.type === "textarea" ? "wrap" : c.type === "date" ? "nowrap" : c.wide || c.type === "dates" || c.type === "suggest" ? "brk" : undefined,
    optional: c.optional,
    mobile: c.mobile ?? (c.type === "textarea" ? "wide" : undefined),
    mlist: c.mlist,
    text: (r: any) => {
      if (c.text) return c.text(r);
      const v = r[c.key];
      if (c.type === "ref") {
        const ref = refMaps[c.ref!]?.get(v);
        return ref ? ref[c.refLabel ?? "name"] : v;
      }
      if (c.type === "bool") return v ? "да" : "нет";
      if (c.type === "date") return v ? String(v).slice(0, 10) : null;
      return v;
    },
  })), [cols, refMaps]);

  const periods = useMemo(() => {
    if (!p.periodKey) return { months: [] as string[], quarters: [] as string[] };
    const ds = (data ?? []).map((x) => (x[p.periodKey!] ?? "").slice(0, 10)).filter(Boolean);
    return {
      months: [...new Set([...ds.map((d) => d.slice(0, 7)), thisMonth()])].sort().reverse(),
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
        <span className="muted">{loading ? "Загрузка…" : `${visible.length} записей`}</span>
        <div className="spacer" />
        {p.periodKey && (
          <>
            {p.periodLabel && <span className="muted small">{p.periodLabel}</span>}
            <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label={p.periodLabel ?? "Период"}>
              <option value="all">Весь период</option>
              {periods.months.map((m) => <option key={m} value={m}>{monthLabel(m)}{m === thisMonth() ? " (текущий)" : ""}</option>)}
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
        {p.toolbar?.(visible, reload)}
        <button className="btn ghost" onClick={() => downloadCsv(p.csvName ?? "export.csv", visible, cols.map((c) => ({ key: c.key, label: c.label })))}>CSV</button>
        {canWrite && p.allowCreate !== false && <button className="btn primary" onClick={() => setEdit({ ...(p.defaults ?? {}) })}>Добавить</button>}
      </div>
      <ErrorLine error={error} />
      <DataTable rows={rows} cols={tableCols} storageKey={p.endpoint} mobileRow={p.mobileRow} filters={p.columnFilters !== false} onRowClick={p.onRowClick} onVisible={setVisible}
        empty={loading ? "Загрузка…" : p.allowCreate === false ? "Пока пусто." : "Пока пусто. Нажмите «Добавить», чтобы создать первую запись."}
        actions={(r) => (<>
          {p.rowActions?.(r, reload)}
          {canWrite && <button className="btn small ghost icon" title="Изменить" aria-label="Изменить" onClick={() => setEdit(r)}><Pencil size={14} aria-hidden /></button>}
        </>)} />
      {edit && (
        <EditForm title={edit.id ? "Изменить" : "Новая запись"} fields={p.fields} initial={edit} onSave={save} onCancel={() => setEdit(null)}
          onDelete={edit.id && can(p.deleteRight ?? "delete") ? () => remove(edit) : undefined} />
      )}
      <Toast text={toast} onDone={() => setToast(null)} />
    </section>
  );
}

