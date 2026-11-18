import { useEffect, useState } from "react";

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={"modal" + (wide ? " wide" : "")} role="dialog" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Закрыть">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Pill({ status }: { status: string | null | undefined }) {
  const s = status ?? "—";
  const cls: Record<string, string> = {
    "В работе": "warn", Пауза: "mute", Сдан: "ok", Выполнено: "ok", Отмена: "bad", Перенос: "mute",
    "Принято в работу": "info", "В процессе": "warn", "CV отправлены": "info",
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
  return text ? <div className="toast" role="status">{text}</div> : null;
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
