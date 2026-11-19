import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  useEffect(() => {
    // keep the page behind still while a dialog is open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);
  // rendered into <body>: glass panels create their own stacking context, so a dialog inside them would be placed
  // relative to the panel instead of the screen
  return createPortal(
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={"modal" + (wide ? " wide" : "")} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Закрыть">×</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
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
    "В работе": "warn", Пауза: "mute", Сдан: "ok", Выполнено: "ok", Отмена: "bad", Перенос: "mute",
    "Принято в работу": "info", "В процессе": "warn",
    "Not Verified": "warn", "Отправлен клиенту": "info", Paid: "ok", Оплачено: "ok", "К оплате": "bad",
    Ожидается: "warn", "В Form 26AS": "info", Зачтён: "ok",
  };
  return <span className={"pill " + (cls[s] ?? "mute")}>{s}</span>;
}

export function ErrorLine({ error }: { error: string | null }) {
  return error ? <p className="error" role="alert">{error}</p> : null;
}

export function Toast({ text, onDone }: { text: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!text) return;
    const t = setTimeout(onDone, 3500);
    return () => clearTimeout(t);
  }, [text, onDone]);
  return text ? createPortal(<div className="toast" role="status">{text}</div>, document.body) : null;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
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
