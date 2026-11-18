import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { EditForm, Field } from "../components/CrudTable";
import { ErrorLine, Modal, useAsync } from "../components/ui";
import { invalidateRef } from "../refs";

const ROLE_L: Record<string, string> = { admin: "админ", accountant: "бухгалтер", manager: "менеджер", archived: "архив" };
const fields: Field[] = [
  { key: "name", label: "Имя", required: true },
  { key: "email", label: "Email", required: true },
  { key: "initials", label: "Инициалы («Чья»)", required: true },
  { key: "role", label: "Роль", type: "select", options: ["manager", "accountant", "admin", "archived"], required: true },
  { key: "active", label: "Активен", type: "bool" },
];

export default function Users() {
  const { can } = useAuth();
  const { data, error, reload } = useAsync(() => api.get<any[]>("/users"), []);
  const [edit, setEdit] = useState<any | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  if (!can("users")) return <div className="page"><p>Раздел доступен только админу.</p></div>;

  const save = async (d: any) => {
    const r = d.id ? await api.patch(`/users/${d.id}`, d) : await api.post("/users", d);
    invalidateRef("users");
    setEdit(null);
    if (r.temp_password) setSecret(`Временный пароль для ${r.email}: ${r.temp_password}`);
    reload();
  };
  return (
    <div className="page">
      <header className="page-head"><h1>Пользователи</h1></header>
      <section className="card">
        <div className="toolbar"><h2>Команда</h2><div className="spacer" /><button className="btn primary" onClick={() => setEdit({ role: "manager", active: true })}>Добавить</button></div>
        <ErrorLine error={error} />
        <table>
          <thead><tr><th>Чья</th><th>Имя</th><th>Email</th><th>Роль</th><th>2FA</th><th>Статус</th><th /></tr></thead>
          <tbody>
            {(data ?? []).map((u) => (
              <tr key={u.id}>
                <td><span className="avatar">{u.initials}</span></td><td>{u.name}</td><td>{u.email}</td><td>{ROLE_L[u.role]}</td>
                <td>{u.totp_enabled ? "включена" : "—"}</td><td>{u.active ? "активен" : "отключён"}</td>
                <td className="actions">
                  <button className="btn small ghost" onClick={() => setEdit(u)}>Изменить</button>
                  {u.role !== "archived" && <button className="btn small ghost" onClick={async () => { const r = await api.post(`/users/${u.id}/reset-password`); setSecret(`Новый временный пароль для ${u.email}: ${r.temp_password}`); }}>Сбросить пароль</button>}
                  {u.totp_enabled && <button className="btn small ghost" onClick={async () => { await api.post(`/users/${u.id}/reset-totp`); reload(); }}>Сбросить 2FA</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {edit && <EditForm title={edit.id ? "Изменить пользователя" : "Новый пользователь"} fields={fields} initial={edit} onSave={save} onCancel={() => setEdit(null)} />}
      {secret && <Modal title="Передайте пароль лично" onClose={() => setSecret(null)}><p className="mono">{secret}</p><p className="muted">Пароль показывается один раз. Попросите сменить его после первого входа.</p></Modal>}
    </div>
  );
}
