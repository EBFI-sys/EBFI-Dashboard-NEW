import { useAuth } from "../auth";
import { useRef_ } from "../refs";

/** «Менеджер»: whose requests / jobs to show. "" = everybody, "me" = the signed-in user, or a user id. */
export function OwnerFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const users = useRef_("users");
  const { me } = useAuth();
  return (
    <label className="owner-filter">
      <span className="muted small">Менеджер</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Фильтр по менеджеру (Чья)"
        className={value ? "on" : ""}>
        <option value="">Все</option>
        <option value="me">Мои{me ? ` (${me.initials})` : ""}</option>
        {users.filter((u) => u.role !== "archived" && u.id !== me?.id).map((u) => (
          <option key={u.id} value={String(u.id)}>{u.initials} — {u.name}</option>
        ))}
      </select>
    </label>
  );
}

export function ownerMatch(filter: string, ownerId: number | null | undefined, meId: number | undefined) {
  if (!filter) return true;
  return filter === "me" ? ownerId === meId : ownerId === Number(filter);
}
