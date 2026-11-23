import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/** Is the page this component lives on the one on screen? Pages stay alive in the background (see main.tsx). */
export const ActiveCtx = createContext(true);
export const PageCtx = createContext<{ path: string; label: string }>({ path: "/", label: "" });

type TrayItem = { id: string; title: string; path: string; label: string; restore: () => void; close: () => void };
type Tray = { items: TrayItem[]; put: (t: TrayItem) => void; drop: (id: string) => void };
export const TrayCtx = createContext<Tray>({ items: [], put: () => undefined, drop: () => undefined });

export function TrayProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<TrayItem[]>([]);
  const put = useCallback((t: TrayItem) => setItems((xs) => [...xs.filter((x) => x.id !== t.id), t]), []);
  const drop = useCallback((id: string) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  return <TrayCtx.Provider value={{ items, put, drop }}>{children}</TrayCtx.Provider>;
}

/** Dialogs. A click beside the window, Esc or «_» folds it into the tray at the bottom of the screen with everything
 *  typed in it kept; the tray brings it back, even after looking at other sections. Only «×» or «Отмена» close it. */
export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  const id = useId();
  const [min, setMin] = useState(false);
  const active = useContext(ActiveCtx);
  const page = useContext(PageCtx);
  const tray = useContext(TrayCtx);
  const shown = !min && active;
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!shown) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setMin(true);
    window.addEventListener("keydown", k);
    // keep the page behind still while a dialog is open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", k);
      document.body.style.overflow = prev;
    };
  }, [shown]);
  useEffect(() => {
    if (min) tray.put({ id, title, path: page.path, label: page.label, restore: () => setMin(false), close: () => closeRef.current() });
    else tray.drop(id);
  }, [min, title, page.path]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => tray.drop(id), []); // eslint-disable-line react-hooks/exhaustive-deps
  // phone: the system «back» (swipe from the left edge) closes the dialog instead of leaving the page
  useEffect(() => {
    if (!shown || !window.matchMedia("(max-width: 820px)").matches) return;
    window.history.pushState({ ...(window.history.state ?? {}), ebfiModal: id }, "");
    const pop = () => { if (window.history.state?.ebfiModal !== id) closeRef.current(); };
    window.addEventListener("popstate", pop);
    return () => {
      window.removeEventListener("popstate", pop);
      if (window.history.state?.ebfiModal === id) window.history.back();  // closed with a button: drop our history entry
    };
  }, [shown, id]);
  // rendered into <body>: glass panels create their own stacking context, so a dialog inside them would be placed
  // relative to the panel instead of the screen. While folded it stays mounted (hidden), so nothing typed is lost.
  return createPortal(
    <div className={"modal-back" + (shown ? "" : " folded")} onMouseDown={(e) => e.target === e.currentTarget && setMin(true)}>
      <div className={"modal" + (wide ? " wide" : "")} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <button className="icon-btn modal-back-btn" onClick={onClose} aria-label="Назад" title="Назад">‹</button>
          <h2>{title}</h2>
          <div className="modal-tools">
            <button className="icon-btn small" onClick={() => setMin(true)} aria-label="Свернуть" title="Свернуть в трей — данные сохранятся">–</button>
            <button className="icon-btn" onClick={onClose} aria-label="Закрыть" title="Закрыть">×</button>
          </div>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

/** Folded dialogs, bottom right on every page. */
export function TrayBar({ go }: { go: (path: string) => void }) {
  const { items } = useContext(TrayCtx);
  if (!items.length) return null;
  return createPortal(
    <div className="tray" role="region" aria-label="Свёрнутые окна">
      {items.map((t) => (
        <div key={t.id} className="tray-item">
          <button type="button" className="tray-open" onClick={() => { go(t.path); t.restore(); }} title="Развернуть">
            <span className="tray-dot" />
            <span className="tray-title">{t.title}</span>
            {t.label && <span className="tray-page">{t.label}</span>}
          </button>
          <button type="button" className="tray-x" aria-label="Закрыть окно без сохранения" title="Закрыть без сохранения" onClick={t.close}>×</button>
        </div>
      ))}
    </div>,
    document.body,
  );
}

/** A small floating panel anchored to a button, kept inside the screen (flips above or to the left when needed). */
export function Popover({ anchor, onClose, children, width = 280, className = "" }: {
  anchor: DOMRect; onClose: () => void; children: React.ReactNode; width?: number; className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; maxH: number; up: boolean } | null>(null);
  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 300;
    const vw = window.innerWidth, vh = window.innerHeight, gap = 6, pad = 12;
    const below = vh - anchor.bottom - gap - pad, above = anchor.top - gap - pad;
    const up = h > below && above > below;
    const maxH = Math.max(160, up ? above : below);
    const top = up ? Math.max(pad, anchor.top - gap - Math.min(h, maxH)) : anchor.bottom + gap;
    const left = Math.min(Math.max(pad, anchor.left), vw - width - pad);
    setPos({ top, left, maxH, up });
  }, [anchor, width]);
  useEffect(() => {
    const out = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const t = setTimeout(() => document.addEventListener("mousedown", out));
    document.addEventListener("keydown", esc);
    const scroll = (e: Event) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    window.addEventListener("resize", onClose);
    window.addEventListener("scroll", scroll, true);
    return () => {
      window.removeEventListener("scroll", scroll, true);
      clearTimeout(t);
      document.removeEventListener("mousedown", out);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose]);
  return createPortal(
    <div ref={ref} className={"popover " + (pos?.up ? "up " : "") + className} onClick={(e) => e.stopPropagation()}
      style={{ width, top: pos?.top ?? -9999, left: pos?.left ?? -9999, maxHeight: pos?.maxH, visibility: pos ? "visible" : "hidden" }}>
      {children}
    </div>,
    document.body,
  );
}

export function Portal({ children }: { children: React.ReactNode }) {
  return createPortal(children, document.body);
}

export function Pill({ status }: { status: string | null | undefined }) {
  const s = status ?? "—";
  const cls: Record<string, string> = {
    "В работе": "warn", Пауза: "mute", Завершен: "ok", Сдан: "ok", Выполнено: "ok", Отмена: "bad", Перенос: "mute",
    "Принято в работу": "info", "В процессе": "warn",
    "Not Verified": "warn", "Отправлен клиенту": "info", Paid: "ok", Оплачено: "ok", "К оплате": "bad",
    Ожидается: "warn", "В Form 26AS": "info", Зачтён: "ok",
  };
  return <span className={"pill " + (cls[s] ?? "mute")}>{s}</span>;
}

export function ErrorLine({ error }: { error: string | null }) {
  return error ? <p className="error" role="alert">{error}</p> : null;
}

export function Toast({ text, onDone, undo }: { text: string | null; onDone: () => void; undo?: (() => void) | null }) {
  useEffect(() => {
    if (!text) return;
    const t = setTimeout(onDone, undo ? 6000 : 3500);
    return () => clearTimeout(t);
  }, [text, onDone, undo]);
  return text ? createPortal(
    <div className={"toast" + (undo ? " with-undo" : "")} role="status">
      {text}
      {undo && <button type="button" className="toast-undo" onClick={() => { undo(); onDone(); }}>Отменить</button>}
    </div>, document.body) : null;
}

/** Skeleton rows while a list loads for the first time. */
export function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="sk-row"><span /><span /><span /><span /></div>)}
    </div>
  );
}

/** useState that survives leaving the page, closing a job card and (for "local") restarting the app on the phone.
 *  "session" lasts until the browser tab or the home-screen app is closed. Keys are per user. */
export function usePersisted<T>(key: string, initial: T, kind: "local" | "session" = "local"): [T, (v: T) => void] {
  const store = () => { try { return kind === "local" ? window.localStorage : window.sessionStorage; } catch { return null; } };
  const full = "ebfi.f." + key;
  const [v, setV] = useState<T>(() => {
    try { const raw = store()?.getItem(full); return raw == null ? initial : (JSON.parse(raw) as T); } catch { return initial; }
  });
  const set = useCallback((x: T) => {
    setV(x);
    try { store()?.setItem(full, JSON.stringify(x)); } catch { /* private mode */ }
  }, [full]); // eslint-disable-line react-hooks/exhaustive-deps
  return [v, set];
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  // a page kept in the background refreshes its data when the user comes back to it
  const active = useContext(ActiveCtx);
  const wasActive = useRef(active);
  useEffect(() => {
    if (active && !wasActive.current) setTick((t) => t + 1);
    wasActive.current = active;
  }, [active]);
  useEffect(() => {
    if (!active) return;
    const f = () => setTick((t) => t + 1);
    window.addEventListener("ebfi:refresh", f);
    return () => window.removeEventListener("ebfi:refresh", f);
  }, [active]);
  useEffect(() => {
    let live = true;
    setLoading(true);
    fn()
      .then((d) => live && (setData(d), setError(null)))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData };
}
