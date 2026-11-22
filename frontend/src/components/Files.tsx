import { Download, ExternalLink, FileText, FolderOpen, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "../api";
import { ErrorLine, useAsync } from "./ui";

/** Invoice file in a register row: «Файл» opens it on OneDrive, otherwise «Загрузить». */
export function InvoiceFile({ url, uploadUrl, hasFile, reload }: { url?: string | null; uploadUrl: string; hasFile?: boolean; reload: () => void }) {
  const [busy, setBusy] = useState(false);
  if (url || hasFile) {
    return <a className="btn small ghost" href={url || uploadUrl} target="_blank" rel="noreferrer"><FileText size={13} aria-hidden />Файл</a>;
  }
  return (
    <label className="btn small ghost file-btn" title="PDF уйдёт в реестр на сервере (месяц → имя)">
      {busy ? "Загружаю…" : <><Upload size={13} aria-hidden />Загрузить</>}
      <input type="file" accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx" hidden onChange={async (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        setBusy(true);
        const fd = new FormData();
        fd.append("file", f);
        try { await api.post(uploadUrl, fd); reload(); } catch (err: any) { alert(err.message); } finally { setBusy(false); }
      }} />
    </label>
  );
}

const fmtSize = (b?: number) => (b == null ? "" : b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** «Документы» on the job card: the two subfolders of the job folder on OneDrive, with upload. */
export function JobDocuments({ job, canWrite, onLinked }: { job: any; canWrite: boolean; onLinked: () => void }) {
  const jobId = job.id;
  const { data, error, loading, reload } = useAsync(() => (job.files_enabled ? api.get(`/jobs/${job.id}/files`) : Promise.resolve(null)), [job.id, job.sp_folder_id]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!job.files_enabled) return null;

  const retry = async () => {
    setErr(null);
    try { await api.post(`/jobs/${job.id}/folder`); onLinked(); reload(); } catch (e: any) { setErr(e.message); }
  };
  const upload = async (folder: string, list: FileList | File[]) => {
    setErr(null);
    setBusy(folder);
    try {
      for (const f of Array.from(list)) {
        const fd = new FormData();
        fd.append("folder", folder);
        fd.append("file", f);
        await api.post(`/jobs/${job.id}/files`, fd);
      }
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  };
  const folders = data?.folders ?? {};
  const names = ["Inspection Documents", "Inspection Deliverables"];
  return (
    <section className="card">
      <div className="toolbar">
        <h2>Документы на сервере</h2>
        <div className="spacer" />
        {(data?.url || job.sp_folder_url) && (
          <a className="btn small" href={data?.url || job.sp_folder_url} target="_blank" rel="noreferrer"><FolderOpen size={14} aria-hidden />Открыть папку работы</a>
        )}
      </div>
      {(job.sp_error || error) && (
        <div className="banner">
          {job.sp_error || error} {canWrite && <button className="btn small" onClick={retry}>Повторить</button>}
        </div>
      )}
      <ErrorLine error={err} />
      {loading && !data && <p className="muted">Загружаю список файлов…</p>}
      {data && (
        <div className="docs-grid">
          {names.map((n) => (
            <DropZone key={n} jobId={jobId} name={n} folder={folders[n]} busy={busy === n} canWrite={canWrite} onFiles={(fl) => upload(n, fl)} />
          ))}
        </div>
      )}
    </section>
  );
}

function DropZone({ jobId, name, folder, busy, canWrite, onFiles }: { jobId: number; name: string; folder: any; busy: boolean; canWrite: boolean; onFiles: (f: FileList) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const files: any[] = folder?.files ?? [];
  return (
    <div className={"dropzone" + (over ? " over" : "")}
      onDragOver={(e) => { if (canWrite) { e.preventDefault(); setOver(true); } }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (canWrite && e.dataTransfer.files.length) onFiles(e.dataTransfer.files); }}>
      <div className="dz-head">
        <h3>{name}</h3>
        <span className="muted small">{files.length} файл(ов)</span>
        <div className="spacer" />
        {folder?.url && <a className="icon-link" href={folder.url} target="_blank" rel="noreferrer" title="Открыть папку"><ExternalLink size={14} /></a>}
      </div>
      {files.length === 0 && <p className="muted small">Пусто.{canWrite ? " Перетащите файлы сюда или нажмите «Загрузить» (на телефоне — фото, медиатека или файлы)." : ""}</p>}
      <ul className="dz-list">
        {files.map((f) => (
          <li key={f.url ?? f.name}>
            <a href={f.url} target="_blank" rel="noreferrer" title="Открыть на OneDrive">{f.folder ? "📁 " : ""}{f.name}</a>
            <span className="muted small">{fmtSize(f.size)}{f.by ? ` · ${f.by}` : ""}</span>
            {!f.folder && f.id && <a className="icon-link dl" href={`/api/jobs/${jobId}/files/${encodeURIComponent(f.id)}/download`} title="Скачать" aria-label={`Скачать ${f.name}`}><Download size={15} /></a>}
          </li>
        ))}
      </ul>
      {canWrite && (
        <>
          <button className="btn small" disabled={busy} onClick={() => input.current?.click()}><Upload size={13} aria-hidden />{busy ? "Загружаю…" : "Загрузить"}</button>
          <input ref={input} type="file" multiple hidden onChange={(e) => e.target.files?.length && onFiles(e.target.files)} />
        </>
      )}
    </div>
  );
}

/** Admin: connection check and number sync. */
export function StorageSettings() {
  const { data, error, loading, reload } = useAsync(() => api.get("/files/status"), []);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <section className="card narrow">
      <h2>Хранилище файлов (OneDrive)</h2>
      {loading && <p className="muted">Проверяю связь…</p>}
      <ErrorLine error={error} />
      {data && !data.enabled && <p>Не подключено. {data.message}</p>}
      {data?.enabled && (data.ok
        ? <><p>Связь есть. Корневая папка: {data.root ? <a href={data.root} target="_blank" rel="noreferrer">открыть</a> : "будет создана"}.</p>
            <p className="muted small">Внутри: {data.folders.join(", ") || "пусто"}</p></>
        : <p className="error">Ошибка: {data.message}</p>)}
      <div className="form-actions">
        <button className="btn ghost" onClick={reload}>Проверить ещё раз</button>
        {data?.ok && <button className="btn" onClick={async () => {
          try { const r = await api.post("/files/sync-numbers"); setMsg(`Очереди номеров обновлены по папкам на сервере: ${Object.keys(r.queues).length}`); } catch (e: any) { setMsg(e.message); }
        }}>Сверить номера работ с сервером</button>}
      </div>
      {msg && <p className="muted">{msg}</p>}
    </section>
  );
}
