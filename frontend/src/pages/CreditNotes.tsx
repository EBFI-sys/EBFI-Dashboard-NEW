import { FileText } from "lucide-react";
import { useState } from "react";
import { api, money, today } from "../api";
import { useAuth } from "../auth";
import CrudTable, { Field } from "../components/CrudTable";
import { ErrorLine, Modal, useAsync } from "../components/ui";

/** Credit notes CN-2627-NNN against client invoices. Owner and accountant only. */
export default function CreditNotes() {
  const { can } = useAuth();
  const next = useAsync(() => (can("credit_notes") ? api.get("/credit-notes/next-number") : Promise.resolve(null)), []);
  const [doc, setDoc] = useState<{ cn: any; reload: () => void } | null>(null);
  if (!can("credit_notes")) return <div className="page"><h1>Кредит-ноты</h1><p className="muted">Раздел доступен владельцу и бухгалтеру.</p></div>;
  const fields: Field[] = [
    { key: "number", label: "Номер", hint: "CN-2627-NNN; пусто — следующий по порядку" },
    { key: "date", label: "Дата", type: "date", required: true },
    { key: "sales_invoice_id", label: "Против инвойса", type: "ref", ref: "sales-invoices", refLabel: "number", required: true, list: false },
    { key: "invoice_number", label: "Инвойс", form: false },
    { key: "client_name", label: "Клиент", form: false },
    { key: "jobs", label: "Работы", form: false, render: (r) => r.jobs?.join(", ") || "—", text: (r) => r.jobs?.join(", ") },
    { key: "amount", label: "Сумма", type: "money", currencyKey: "currency", hint: "Пусто — сумма инвойса целиком",
      render: (r) => (r.amount != null ? money(r.amount, r.currency) : "—") },
    { key: "release", label: "Освободить работы для нового инвойса (другой плательщик / исправленный инвойс)", type: "bool", list: false },
    { key: "released", label: "Работы освобождены", type: "bool", form: false, render: (r) => (r.released ? "да" : "—") },
    { key: "reason", label: "Причина", type: "textarea", wide: true },
  ];
  return (
    <div className="page">
      <header className="page-head"><div><h1>Кредит-ноты</h1>
        <p className="lede">Кредит-нота — копия исходного инвойса с заголовком «CREDIT NOTE PASS AGAINST INVOICE №» и своей датой. Сторнированный инвойс не считается к получению. Если работы нужно перевыставить другому плательщику, отметьте «Освободить работы».</p></div></header>
      <CrudTable endpoint="/credit-notes" title="Реестр кредит-нот" fields={fields} csvName="credit-notes.csv" periodKey="date"
        writeRight="credit_notes" deleteRight="credit_notes" defaults={{ date: today(), number: next.data?.number }}
        rowActions={(r, reload) => <button className="btn small" onClick={() => setDoc({ cn: r, reload })}><FileText size={13} aria-hidden />Word / PDF</button>} />
      {doc && <CnDoc cn={doc.cn} onClose={() => setDoc(null)} onDone={doc.reload} />}
    </div>
  );
}

function CnDoc({ cn, onClose, onDone }: { cn: any; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const urls = res ?? cn;
  const dl = (k: string) => `/api/credit-notes/${cn.id}/document/${k}`;
  return (
    <Modal title={`${cn.number} · против ${cn.invoice_number}`} onClose={onClose}>
      <div className="doc-box">
        <p>{cn.client_name} · {cn.jobs?.join(", ")} · {cn.amount != null ? money(cn.amount, cn.currency) : ""}</p>
        {res?.warnings?.length > 0 && <ul className="problems">{res.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>}
        <ErrorLine error={err} />
        <div className="form-actions" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
          <button className="btn primary" disabled={busy} onClick={async () => {
            setBusy(true); setErr(null);
            try { setRes(await api.post(`/credit-notes/${cn.id}/document`)); onDone(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
          }}>{busy ? "Формирую…" : urls.doc_url ? "Сформировать заново" : "Сформировать Word и PDF"}</button>
          <a className="btn ghost" href={dl("docx")}>Скачать Word</a>
          <a className="btn ghost" href={dl("pdf")}>Скачать PDF</a>
        </div>
        {(urls.doc_url || urls.pdf_url) && <p className="small">На сервере (Outgoing Invoice Register / … / Credit Notes):{" "}
          {urls.doc_url && <a href={urls.doc_url} target="_blank" rel="noreferrer">Word</a>}{urls.pdf_url && <> · <a href={urls.pdf_url} target="_blank" rel="noreferrer">PDF</a></>}</p>}
      </div>
    </Modal>
  );
}
