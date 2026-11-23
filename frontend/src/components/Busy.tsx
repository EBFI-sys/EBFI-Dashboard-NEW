import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useRef_ } from "../refs";

const dm = (iso: string) => iso.slice(8, 10) + "." + iso.slice(5, 7);

/** «Инспектор занят»: the chosen inspectors already work on another job on some of these dates. */
export function BusyWarning({ inspectorIds, datesText, excludeJobId }: { inspectorIds: (number | null | undefined)[]; datesText?: string | null; excludeJobId?: number }) {
  const inspectors = useRef_("inspectors");
  const [busy, setBusy] = useState<Record<string, { date: string; job_id: number; job_number: string }[]>>({});
  const ids = inspectorIds.filter(Boolean).map(Number);
  const key = ids.join(",") + "|" + (datesText ?? "") + "|" + (excludeJobId ?? "");
  useEffect(() => {
    if (!ids.length || !datesText?.trim()) { setBusy({}); return; }
    const t = setTimeout(() => {
      api.post("/inspectors/busy", { inspector_ids: ids, dates_text: datesText, exclude_job_id: excludeJobId })
        .then(setBusy).catch(() => setBusy({}));
    }, 400);
    return () => clearTimeout(t);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const entries = Object.entries(busy).filter(([, v]) => v.length);
  if (!entries.length) return null;
  return (
    <div className="busy-warn wide" role="alert">
      <AlertTriangle size={16} aria-hidden />
      <div>
        {entries.map(([id, list]) => {
          const byJob = new Map<string, { id: number; days: string[] }>();
          list.forEach((x) => { const j = byJob.get(x.job_number) ?? { id: x.job_id, days: [] }; j.days.push(dm(x.date)); byJob.set(x.job_number, j); });
          return (
            <p key={id}>
              <b>{inspectors.find((i) => i.id === Number(id))?.name ?? `Инспектор #${id}`}</b> уже занят:{" "}
              {[...byJob.entries()].map(([no, j], i) => (
                <span key={no}>{i > 0 && "; "}{j.days.join(", ")} — <Link to={`/jobs/${j.id}`} onClick={(e) => e.stopPropagation()}>{no}</Link></span>
              ))}
            </p>
          );
        })}
      </div>
    </div>
  );
}
