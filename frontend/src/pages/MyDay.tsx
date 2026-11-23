import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ClientChip } from "../components/Chips";
import { ErrorLine, Pill, Skeleton, useAsync, usePersisted } from "../components/ui";
import { useRef_ } from "../refs";
import { surnames } from "./Jobs";

const dm = (iso?: string | null) => (iso ? iso.slice(8, 10) + "." + iso.slice(5, 7) : "");

function Section({ title, hint, items, empty, children }: { title: string; hint?: string; items: any[]; empty: string; children: (x: any) => React.ReactNode }) {
  return (
    <section className="card myday-sec">
      <div className="toolbar"><h2>{title}</h2><span className="count-badge">{items.length}</span>{hint && <span className="muted small">{hint}</span>}</div>
      {items.length === 0 ? <p className="muted small">{empty}</p> : <ul className="myday-list">{items.map(children)}</ul>}
    </section>
  );
}

/** «Мой день»: what the manager has to do today, the same lists as the 09:00 Telegram digest. */
export default function MyDay() {
  const nav = useNavigate();
  const { me } = useAuth();
  const users = useRef_("users");
  const [scope, setScope] = usePersisted<"me" | "all">("myday.scope", "me");
  const { data, error, loading } = useAsync(() => api.get(`/my-day?scope=${scope}`), [scope]);
  const owner = (id: number) => (scope === "all" ? users.find((u) => u.id === id)?.initials : null);
  const job = (j: any, right: React.ReactNode) => (
    <li key={j.id + String(right)} onClick={() => nav(`/jobs/${j.id}`)} className="clickable">
      <div className="lrow lrow-job">
        <Pill status={j.status} /><b className="lrow-no mono">{j.job_number}</b>
        <span className="lrow-right"><ClientChip name={j.client} /></span>
        <span className="lrow-sub">{[surnames(j.inspector), j.country, owner(j.owner_id)].filter(Boolean).join(" · ") || "—"}</span>
        <span className="lrow-right lrow-dates">{right}</span>
      </div>
    </li>
  );
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Мой день</h1>
          {data && <p className="lede">{new Date(data.date).toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" })}{me ? ` · ${me.name.split(" ")[0]}` : ""}</p>}</div>
        <div className="seg">
          <button className={scope === "me" ? "on" : ""} onClick={() => setScope("me")}>Мои</button>
          <button className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>Все</button>
        </div>
      </header>
      <ErrorLine error={error} />
      {loading && !data && <section className="card"><Skeleton rows={6} /></section>}
      {data && (
        <div className="myday">
          <Section title="Инспекции сегодня и завтра" items={data.today_tomorrow} empty="Сегодня и завтра инспекций нет.">
            {(j) => job(j, j.when)}
          </Section>
          <Section title="Отчёты за вчера — сдать клиенту" hint={dm(data.yesterday)} items={data.reports} empty="Вчера инспекций не было.">
            {(j) => job(j, dm(data.yesterday))}
          </Section>
          <Section title="Пора завершить" hint="все даты прошли, статус не «Завершен»" items={data.to_close} empty="Всё завершено.">
            {(j) => job(j, `посл. ${dm(j.last_date)}`)}
          </Section>
          <Section title="Заявки в процессе" hint="CV / предложение клиенту не отправлены" items={data.requests} empty="Нет заявок в процессе.">
            {(r) => (
              <li key={r.id} onClick={() => nav("/requests")} className="clickable">
                <div className="lrow">
                  <Pill status="В процессе" /><b className="lrow-no">{r.client ?? "—"}</b>
                  <span className="lrow-right muted">{r.days != null ? `ждёт ${r.days} дн.` : ""}</span>
                  <span className="lrow-sub">{[r.country, r.factory, owner(r.owner_id)].filter(Boolean).join(" · ") || "—"}</span>
                  <span className="lrow-right lrow-dates">{r.dates ?? ""}</span>
                </div>
              </li>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
