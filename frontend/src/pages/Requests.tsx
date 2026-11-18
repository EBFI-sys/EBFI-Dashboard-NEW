import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import CrudTable, { Field } from "../components/CrudTable";
import { ErrorLine, Modal } from "../components/ui";
import { CURRENCIES } from "../refs";

export const REQ_STATUSES = ["В процессе", "CV отправлены", "Принято в работу", "Выполнено", "Перенос", "Отмена"];

const fields: Field[] = [
  { key: "received_date", label: "Дата", type: "date" },
  { key: "type", label: "Тип", type: "select", options: ["Inspection", "Audit", "Expediting"], required: true },
  { key: "client_id", label: "Клиент", type: "ref", ref: "clients", required: true },
  { key: "final_client", label: "Конечный клиент", list: false },
  { key: "country", label: "Страна", type: "suggest", ref: "countries", required: true },
  { key: "factory", label: "Завод / адрес", type: "suggest", ref: "vendors", wide: true },
  { key: "dates_text", label: "Даты", type: "dates" },
  { key: "client_rate", label: "Нам платят", type: "money", currencyKey: "client_currency" },
  { key: "client_currency", label: "Валюта клиента", type: "select", options: CURRENCIES, list: false },
  { key: "inspector_rate", label: "Ставка инспектора", type: "money", currencyKey: "inspector_currency" },
  { key: "inspector_currency", label: "Валюта инспектора", type: "select", options: CURRENCIES, list: false },
  { key: "inspector_id", label: "Инспектор", type: "ref", ref: "inspectors" },
  { key: "proposed_cvs", label: "Отправленные CV", type: "textarea", list: false },
  { key: "status", label: "Статус", type: "status", options: REQ_STATUSES, required: true },
  { key: "cancel_reason", label: "Причина отмены / переноса", wide: true, list: false, hint: "Обязательно для статусов «Отмена» и «Перенос»" },
  { key: "owner_id", label: "Чья", type: "ref", ref: "users", refLabel: "initials" },
  { key: "notes", label: "Примечания", type: "textarea", list: false },
];

export default function Requests() {
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [mk, setMk] = useState<any | null>(null);
  return (
    <div className="page">
      <header className="page-head"><h1>Заявки</h1></header>
      <CrudTable
        endpoint="/requests"
        title={onlyOpen ? "Открытые заявки" : "Все заявки"}
        fields={fields}
        csvName="requests.csv"
        defaults={{ status: "В процессе", type: "Inspection", received_date: new Date().toISOString().slice(0, 10), client_currency: "USD", inspector_currency: "USD" }}
        filter={(r) => !onlyOpen || !["Выполнено", "Отмена"].includes(r.status)}
        toolbar={() => (
          <label className="check"><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> только открытые</label>
        )}
        rowActions={(r, reload) =>
          r.job_id ? <Link className="btn small ghost" to={`/jobs/${r.job_id}`}>В табеле</Link>
            : !["Отмена", "Выполнено"].includes(r.status) && <button className="btn small" onClick={() => setMk({ r, reload })}>Создать работу</button>
        }
      />
      {mk && <CreateJob req={mk.r} onClose={() => setMk(null)} onDone={mk.reload} />}
    </div>
  );
}

function CreateJob({ req, onClose, onDone }: { req: any; onClose: () => void; onDone: () => void }) {
  const nav = useNavigate();
  const [no, setNo] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const go = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const job = await api.post(`/requests/${req.id}/create-job`, { job_number: no });
      onDone();
      nav(`/jobs/${job.id}`);
    } catch (e: any) {
      setErr(e.message);
    }
  };
  return (
    <Modal title="Создать работу из заявки" onClose={onClose}>
      <form onSubmit={go} className="form-grid">
        <label className="field wide"><span>Job number</span>
          <input autoFocus placeholder="26.19-478" value={no} onChange={(e) => setNo(e.target.value)} />
          <small>Формат ГГ.КК-ННН. Клиент, страна и завод перенесутся из заявки.</small>
        </label>
        <ErrorLine error={err} />
        <div className="form-actions wide">
          <button type="button" className="btn ghost" onClick={onClose}>Отмена</button>
          <button className="btn primary">Создать</button>
        </div>
      </form>
    </Modal>
  );
}
