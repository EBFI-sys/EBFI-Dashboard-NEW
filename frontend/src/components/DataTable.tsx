import { useEffect, useMemo, useState } from "react";
import { Popover } from "./ui";

/** One column of a DataTable. `text` gives the value used for filtering and sorting (defaults to row[key]). */
export type Col = {
  key: string;
  label: string;
  render?: (row: any) => React.ReactNode;
  text?: (row: any) => string | number | null | undefined;
  align?: "r";
  cls?: string;
  filter?: boolean; // default true
  sortNumeric?: boolean;
  optional?: boolean; // hidden until the user turns it on in «Столбцы»
  total?: (rows: any[]) => React.ReactNode; // footer cell for this column
  mobile?: "head" | "wide" | "hide"; // phone card view: in the card title, full width, or not shown
};

type Props = {
  rows: any[];
  cols: Col[];
  rowKey?: (row: any) => string | number;
  onRowClick?: (row: any) => void;
  rowClass?: (row: any) => string | undefined;
  rowTitle?: (row: any) => string | undefined;
  actions?: (row: any) => React.ReactNode;
  empty?: React.ReactNode;
  filters?: boolean; // Excel-style filters in the header (default true)
  onVisible?: (rows: any[]) => void; // rows left after filters, e.g. for totals or CSV
  footer?: (rows: any[]) => React.ReactNode;
  className?: string;
  storageKey?: string; // remembers which optional columns are shown
  footLabel?: (rows: any[]) => React.ReactNode; // first footer cell when columns have totals
};

function loadShown(key?: string): string[] | null {
  if (!key) return null;
  try {
    const v = localStorage.getItem("ebfi.cols." + key);
    return v ? JSON.parse(v) : null;
  } catch {
    return null;
  }
}

function ColumnPicker({ cols, shown, setShown }: { cols: Col[]; shown: Set<string>; setShown: (s: Set<string>) => void }) {
  const [open, setOpen] = useState<DOMRect | null>(null);
  const extra = cols.filter((c) => c.optional);
  const on = extra.filter((c) => shown.has(c.key)).length;
  return (
    <div className="colpick">
      <button type="button" className="btn small ghost" onClick={(e) => setOpen(open ? null : e.currentTarget.getBoundingClientRect())} aria-expanded={!!open}>
        Столбцы{on ? ` · +${on}` : ""} ▾
      </button>
      {open && (
        <Popover anchor={open} onClose={() => setOpen(null)} width={250} className="colpick-menu">
          <p className="muted small">Дополнительные столбцы</p>
          {extra.map((c) => (
            <label key={c.key} className="fmenu-item">
              <input type="checkbox" checked={shown.has(c.key)} onChange={() => {
                const n = new Set(shown);
                n.has(c.key) ? n.delete(c.key) : n.add(c.key);
                setShown(n);
              }} />
              <span className="fmenu-val">{c.label}</span>
            </label>
          ))}
          <div className="fmenu-foot">
            <button type="button" className="btn small ghost" onClick={() => setShown(new Set())}>Скрыть все</button>
            <button type="button" className="btn small ghost" onClick={() => setShown(new Set(extra.map((c) => c.key)))}>Показать все</button>
          </div>
        </Popover>
      )}
    </div>
  );
}

const BLANK = "(пусто)";
const asText = (v: unknown) => (v === null || v === undefined || v === "" ? BLANK : String(v));

function valueOf(c: Col, row: any) {
  return c.text ? c.text(row) : row[c.key];
}

function FilterMenu({ col, rows, selected, onChange, onSort, close, at }: {
  col: Col; rows: any[]; selected: Set<string> | undefined; onChange: (s: Set<string> | undefined) => void;
  onSort: (dir: 1 | -1) => void; close: () => void; at: DOMRect;
}) {
  const [q, setQ] = useState("");
  const values = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of rows) {
      const t = asText(valueOf(col, r));
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    const num = col.sortNumeric || col.align === "r";
    return [...counts.entries()].sort((a, b) =>
      num ? Number(a[0]) - Number(b[0]) || a[0].localeCompare(b[0]) : a[0].localeCompare(b[0], "ru"));
  }, [rows, col]);
  const shown = values.filter(([v]) => !q || v.toLowerCase().includes(q.toLowerCase()));
  const isOn = (v: string) => !selected || selected.has(v);

  const toggle = (v: string) => {
    const s = new Set(selected ?? values.map(([x]) => x));
    s.has(v) ? s.delete(v) : s.add(v);
    onChange(s.size === values.length ? undefined : s);
  };
  const allShownOn = shown.every(([v]) => isOn(v));
  const toggleShown = () => {
    const s = new Set(selected ?? values.map(([x]) => x));
    for (const [v] of shown) allShownOn ? s.delete(v) : s.add(v);
    onChange(s.size === values.length ? undefined : s);
  };

  return (
    <Popover anchor={at} onClose={close} width={280} className="fmenu">
      <div className="fmenu-sort">
        <button type="button" onClick={() => { onSort(1); close(); }}>Сортировать А → Я ↑</button>
        <button type="button" onClick={() => { onSort(-1); close(); }}>Сортировать Я → А ↓</button>
      </div>
      <input autoFocus placeholder="Поиск значений" aria-label={`Поиск в столбце ${col.label}`} value={q} onChange={(e) => setQ(e.target.value)} />
      <label className="fmenu-item all">
        <input type="checkbox" checked={allShownOn} onChange={toggleShown} />
        {q ? "Все найденные" : "Выбрать все"}
      </label>
      <div className="fmenu-list">
        {shown.map(([v, n]) => (
          <label key={v} className="fmenu-item">
            <input type="checkbox" checked={isOn(v)} onChange={() => toggle(v)} />
            <span className="fmenu-val">{v}</span>
            <span className="muted">{n}</span>
          </label>
        ))}
        {shown.length === 0 && <p className="muted small">Ничего не найдено</p>}
      </div>
      <div className="fmenu-foot">
        <button type="button" className="btn small ghost" onClick={() => { onChange(undefined); close(); }}>Очистить</button>
        {q && shown.length > 0 && (
          <button type="button" className="btn small" onClick={() => { onChange(new Set(shown.map(([v]) => v))); close(); }}>Только найденные</button>
        )}
        <button type="button" className="btn small primary" onClick={close}>Готово</button>
      </div>
    </Popover>
  );
}

export default function DataTable({ rows, cols: allCols, rowKey, onRowClick, rowClass, rowTitle, actions, empty, filters = true, onVisible, footer, className, storageKey, footLabel }: Props) {
  const [shownExtra, setShownExtra] = useState<Set<string>>(() => new Set(loadShown(storageKey) ?? []));
  const saveShown = (s: Set<string>) => {
    setShownExtra(s);
    try {
      if (storageKey) localStorage.setItem("ebfi.cols." + storageKey, JSON.stringify([...s]));
    } catch {
      /* private window */
    }
  };
  const cols = useMemo(() => allCols.filter((c) => !c.optional || shownExtra.has(c.key)), [allCols, shownExtra]);
  const hasOptional = allCols.some((c) => c.optional);
  const hasTotals = cols.some((c) => c.total);
  const [sel, setSel] = useState<Record<string, Set<string> | undefined>>({});
  const [open, setOpen] = useState<{ key: string; at: DOMRect } | null>(null);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);

  const visible = useMemo(() => {
    let r = rows.filter((row) => cols.every((c) => !sel[c.key] || sel[c.key]!.has(asText(valueOf(c, row)))));
    if (sort) {
      const c = cols.find((x) => x.key === sort.key);
      if (c) {
        const num = c.sortNumeric || c.align === "r";
        r = [...r].sort((a, b) => {
          const va = valueOf(c, a), vb = valueOf(c, b);
          if (va == null || va === "") return 1;
          if (vb == null || vb === "") return -1;
          return (num ? Number(va) - Number(vb) : String(va).localeCompare(String(vb), "ru")) * sort.dir;
        });
      }
    }
    return r;
  }, [rows, cols, sel, sort]);

  useEffect(() => onVisible?.(visible), [visible, onVisible]);
  const active = Object.values(sel).filter(Boolean).length;
  const span = cols.length + (actions ? 1 : 0);

  return (
    <div className={"table-wrap " + (className ?? "")}>
      {((filters && active > 0) || hasOptional) && (
        <div className="filter-note">
          {filters && active > 0 && <>
            Фильтров: {active} · показано {visible.length} из {rows.length}
            <button type="button" className="btn small ghost" onClick={() => setSel({})}>Сбросить фильтры</button>
          </>}
          <span className="spacer" />
          {hasOptional && <ColumnPicker cols={allCols} shown={shownExtra} setShown={saveShown} />}
        </div>
      )}
      <table className="mcards">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={(c.align === "r" ? "r " : "") + "th"}>
                <span className="th-in">
                  <button type="button" className="th-label" onClick={() => setSort({ key: c.key, dir: sort?.key === c.key ? (-sort.dir as 1 | -1) : 1 })}>
                    {c.label}{sort?.key === c.key ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                  </button>
                  {filters && c.filter !== false && (
                    <button type="button" className={"th-filter" + (sel[c.key] ? " on" : "")} aria-label={`Фильтр по столбцу ${c.label}`}
                      onClick={(e) => { e.stopPropagation(); setOpen(open?.key === c.key ? null : { key: c.key, at: e.currentTarget.getBoundingClientRect() }); }}>▾</button>
                  )}
                </span>
                {open?.key === c.key && (
                  <FilterMenu col={c} rows={rows} selected={sel[c.key]} close={() => setOpen(null)} at={open.at}
                    onChange={(s) => setSel((x) => ({ ...x, [c.key]: s }))} onSort={(dir) => setSort({ key: c.key, dir })} />
                )}
              </th>
            ))}
            {actions && <th />}
          </tr>
        </thead>
        <tbody>
          {visible.map((r, i) => (
            <tr key={rowKey ? rowKey(r) : r.id ?? i} className={[onRowClick ? "clickable" : "", rowClass?.(r) ?? ""].join(" ").trim()} title={rowTitle?.(r)} onClick={() => onRowClick?.(r)}>
              {cols.map((c) => (
                <td key={c.key} data-label={c.label} className={(c.align === "r" ? "r " : "") + (c.cls ?? "") + (c.mobile ? " m-" + c.mobile : "")}>
                  {c.render ? c.render(r) : (r[c.key] ?? "—")}
                </td>
              ))}
              {actions && <td className="actions" onClick={(e) => e.stopPropagation()}>{actions(r)}</td>}
            </tr>
          ))}
          {visible.length === 0 && <tr><td colSpan={span} className="empty">{rows.length ? "Под фильтры ничего не подходит." : empty ?? "Нет данных."}</td></tr>}
        </tbody>
        {footer && visible.length > 0 && <tfoot>{footer(visible)}</tfoot>}
        {!footer && hasTotals && visible.length > 0 && (
          <tfoot>
            <tr>
              {cols.map((c, i) => (
                <td key={c.key} className={c.align === "r" ? "r" : ""}>{c.total ? c.total(visible) : i === 0 ? footLabel?.(visible) : null}</td>
              ))}
              {actions && <td />}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
