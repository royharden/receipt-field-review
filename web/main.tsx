import { useEffect, useRef, useState } from "react";
import type { Action, ApiStatus, Currency, DecisionDraft, ExportFile, ExportMode, ItemDetail,
  ImageJobStart, ItemSummary, JobRecord, Json, StagedImage } from "./contracts";
import { ApiError, HttpReviewApi, IMAGE_LIMIT, describeError, imageDigest } from "./http";
import { SourcePreview } from "./source-preview";

const display = (value: Json | undefined) => value == null ? "—" :
  typeof value === "string" ? value : JSON.stringify(value);
const message = describeError;
const batchHash = () => {
  const value = new URLSearchParams(location.hash.slice(1)).get("batch") ?? "";
  return /^[a-f0-9]{32}$/.test(value) ? value : "";
};

type Edit = { action: Action; value: string; reason: string; issues: string[]; issueReason: string };

export function Review({ api, batch, detail, changed, lock, disabled = false }: {
  api: Pick<HttpReviewApi, "draft" | "apply" | "item" | "image">; batch: string; detail: ItemDetail;
  changed: (value: ItemDetail) => Promise<void>; lock: (value: boolean) => void;
  disabled?: boolean;
}) {
  const view = detail.review;
  const fields = Object.entries(view.fields);
  const [selected, setSelected] = useState(view.unfinished_fields[0] ?? fields[0]?.[0] ?? "");
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [actor, setActor] = useState("local reviewer");
  const [human, setHuman] = useState(false);
  const [actorRef, setActorRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState<{ field: string; draft: DecisionDraft } | null>(null);
  const submit = useRef<() => void>(() => {});
  useEffect(() => {
    lock(busy || !!pending || Object.keys(edits).length > 0);
    return () => lock(false);
  }, [busy, pending, edits, lock]);
  const field = view.fields[selected];
  const edit: Edit = edits[selected] ?? { action: "correct", value: display(field?.effective_value) === "—" ?
    display(field?.machine.proposal) === "—" ? "" : display(field?.machine.proposal) : display(field?.effective_value),
    reason: "", issues: [], issueReason: "" };
  const update = (values: Partial<Edit>) => setEdits(old => ({ ...old, [selected]: { ...edit, ...values } }));
  const valid = !!field && !!actor.trim() && !!edit.reason.trim() && (!human || !!actorRef.trim()) &&
    (!edit.issues.length || !!edit.issueReason.trim()) && (edit.action !== "correct" || !!edit.value.trim());

  async function refresh() {
    if (disabled) return;
    setBusy(true); setError("");
    try { await changed(await api.item(batch, view.item_id)); setConflict(false); setPending(null); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function save(retry = false) {
    if (disabled || busy || conflict || (!retry && (pending !== null || !valid)) || (retry && pending === null)) return;
    setBusy(true); setError(""); setNotice("");
    let committed = false;
    try {
      const saved = retry && pending ? pending : { field: selected, draft: await api.draft(batch, view.item_id, {
        field_id: selected, action: edit.action, value: edit.action === "correct" ? edit.value : null,
        expected_item_revision: view.revision, expected_prior_event_id: field?.head_event_id ?? null,
        actor: actor.trim(), actor_kind: human ? "human_claimed" : "agent_provisional",
        actor_ref: human ? actorRef.trim() : null, reason: edit.reason.trim(),
        waive_issues: edit.issues, issue_reason: edit.issues.length ? edit.issueReason.trim() : null,
      }) };
      setPending(saved);
      const receipt = await api.apply(batch, view.item_id, saved.draft);
      committed = true;
      setPending(null); setEdits(old => { const copy = { ...old }; delete copy[saved.field]; return copy; });
      setNotice(`${receipt.outcome === "exact_retry" ? "Already saved" : "Decision saved"}. Journal event ${receipt.event_id}`);
      await changed(await api.item(batch, view.item_id));
    } catch (e) {
      setError(committed ? "Decision saved, but state refresh failed. Reload state before another edit." : message(e));
      if (committed || (e instanceof ApiError && e.status === 409)) setConflict(true);
    }
    finally { setBusy(false); }
  }
  submit.current = () => { void save(pending !== null); };
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); submit.current(); }
    };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, []);

  return <>
    <div className="review-heading"><div><span className="eyebrow">Receipt review</span><h1>{display(view.fields.merchant_name?.effective_value) === "—" ?
      display(view.fields.merchant_name?.machine.proposal) : display(view.fields.merchant_name?.effective_value)}</h1>
      <p className="mono">{view.item_id}</p></div>
      <div><span className={`tag ${view.clean ? "clean" : "review-only"}`}>{view.clean ? "Operationally resolved" : "Review required"}</span>
        <p className="muted">{view.unfinished_fields.length} unfinished · {view.unresolved_issues.length} unresolved issues</p></div></div>
    <div className="review-grid"><SourcePreview api={api} batch={batch} detail={detail} field={field} />
      <section className="review-pane" aria-label="Fields and decisions">
        <div className="section-title"><h2>Fields & line cells</h2><button disabled={busy || disabled} onClick={() => void refresh()}>Reload state</button></div>
        <p className="muted">Every scalar, line cell and adjustment remains visible. Select a field to review it.</p>
        <div className="fields" aria-label="Receipt fields">{fields.map(([id, value]) => <button type="button" key={id}
          className={`field ${id === selected ? "selected" : ""}`} disabled={busy || disabled || !!pending}
          aria-pressed={id === selected} onClick={() => { setSelected(id); setError(""); setNotice(""); }}>
          <span><strong>{id.replaceAll("_", " ")}</strong><small>{value.review_state}</small></span>
          <span>{display(value.effective_value) === "—" ? display(value.machine.proposal) : display(value.effective_value)}</span>
        </button>)}</div>
        {field && <div className="editor"><h3>{selected.replaceAll("_", " ")}</h3>
          <dl><dt>Machine proposal</dt><dd>{display(field.machine.proposal)}</dd><dt>Effective value</dt><dd>{display(field.effective_value)}</dd>
            <dt>Diagnostic score</dt><dd>{field.machine.confidence ?? "Unavailable"} · uncalibrated</dd>
            <dt>Method / label</dt><dd>{field.machine.method} / {field.label?.label_source ?? "unlabelled"}</dd></dl>
          {field.conflict && <p role="alert" className="error">Conflict: {field.conflict}</p>}
          <fieldset disabled={busy || disabled || !!pending || conflict}><legend>Explicit decision</legend>
            <label>Action<select value={edit.action} onChange={e => update({ action: e.target.value as Action })}>
              <option value="correct">Correct value</option><option value="confirm">Confirm current proposal/value</option>
              <option value="waive_absent">Waive as printed absent</option><option value="reopen">Reopen for review</option></select></label>
            {edit.action === "correct" && <label>Corrected value<input value={edit.value} maxLength={4096}
              onChange={e => update({ value: e.target.value })} /></label>}
            <label>Decision reason<textarea value={edit.reason} maxLength={4096} rows={2}
              onChange={e => update({ reason: e.target.value })} /></label>
            <details><summary>Reviewer and issue disposition</summary>
              <label>Reviewer name<input value={actor} maxLength={512} onChange={e => setActor(e.target.value)} /></label>
              <label className="check"><input type="checkbox" checked={human} onChange={e => setHuman(e.target.checked)} />Claimed human reviewer</label>
              {human && <label>Reviewer reference<input value={actorRef} maxLength={512} onChange={e => setActorRef(e.target.value)} /></label>}
              <p className="muted">Default: agent-provisional. A human claim stays unverified and does not establish independent Gold.</p>
              {view.unresolved_issues.map(issue => <label className="check" key={issue}><input type="checkbox"
                checked={edit.issues.includes(issue)} onChange={e => update({ issues: e.target.checked ?
                  [...edit.issues, issue] : edit.issues.filter(x => x !== issue) })} />Explicitly waive: {issue}</label>)}
              {!!edit.issues.length && <label>Issue waiver reason<textarea rows={2} value={edit.issueReason}
                maxLength={1024} onChange={e => update({ issueReason: e.target.value })} /></label>}
            </details>
          </fieldset>
          <div className="actions"><button className="primary" disabled={busy || disabled || !valid || !!pending || conflict}
            onClick={() => void save()}>Save decision</button>
            {pending && <button disabled={busy || disabled || conflict} onClick={() => void save(true)}>Retry saved decision</button>}
            <span className="muted">{pending ? "Ctrl + Enter to retry saved decision" : "Ctrl + Enter to save"}</span></div>
          {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status" className="success">{notice}</p>}
          {!!Object.keys(edits).length && <button disabled={busy || disabled || !!pending} onClick={() => setEdits({})}>Discard unsaved edits</button>}
          <p className="muted">Edits stay in memory until saved. Reload state keeps your text, but clears a pending retry. Reload the page only after saving.</p>
        </div>}
      </section></div>
    <section className="checks"><h2>Checks & unresolved issues</h2><p>Correcting a value never silently waives a hard issue. Resolved exports may include explicit waivers.</p>
      {view.checks.map(check => <div key={check.check_id} className="check-row"><span className="tag">{check.status}</span>
        <strong>{check.check_id}</strong><span>{check.reason ?? "No diagnostic reason"}</span></div>)}
      {!!view.unresolved_issues.length && <ul>{view.unresolved_issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
    </section>
  </>;
}

type ImageRow = { name: string; file: File | null; bytes?: Blob; sha?: string;
  staged?: StagedImage; selected: boolean; omitted?: boolean; error?: string };
type FrozenImageRequest = { request: ImageJobStart; jobId: string };
const terminalImageJob = (job: JobRecord | null) => !!job && !["pending", "running"].includes(job.state);
const referenceDay = (day: string) => /^\d{4}-\d{2}-\d{2}$/.test(day) &&
  !Number.isNaN(new Date(day + "T00:00:00Z").getTime()) && new Date(day + "T00:00:00Z").toISOString().slice(0, 10) === day;

/** One in-memory image cohort. Only persisted JobRecord outcomes become review items. */
export function ImageImport({ api, batch, uploadAvailable, workerAvailable, disabled, lock, settled }: {
  api: Pick<HttpReviewApi, "stageImage" | "startImageJob" | "imageJob" | "items">;
  batch: string; uploadAvailable: boolean; workerAvailable: boolean; disabled: boolean;
  lock: (value: boolean) => void; settled: () => Promise<void>;
}) {
  const [rows, setRows] = useState<ImageRow[]>([]);
  const [day, setDay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<FrozenImageRequest | null>(null);
  const [job, setJob] = useState<JobRecord | null>(null);
  const running = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    lock(busy || rows.length > 0 || pending !== null);
    return () => lock(false);
  }, [busy, rows.length, pending, lock]);
  const updateRow = (index: number, patch: Partial<ImageRow>) => {
    if (mounted.current) setRows(old => old.map((row, i) => i === index ? { ...row, ...patch } : row));
  };
  function choose(files: FileList | null) {
    if (disabled || running.current || rows.length || pending || !files) return;
    const selected = Array.from(files);
    if (!selected.length || selected.length > 100 || selected.some(f => f.size < 1 || f.size > IMAGE_LIMIT)) {
      setError("Choose 1–100 JPEG, PNG or HEIC images, each nonempty and at most 20 MiB. Nothing was uploaded."); return;
    }
    setError(""); setRows(selected.map(file => ({ name: file.name, file, selected: true })));
  }
  async function stage() {
    if (disabled || running.current || pending || !uploadAvailable) return;
    running.current = true; setBusy(true); setError("");
    const seen = new Set(rows.flatMap(r => r.staged ? [r.staged.original_sha256] : []));
    try {
      for (const [index, row] of rows.entries()) {
        if (!mounted.current) break;
        if (row.staged || row.omitted || !row.file) continue;
        try {
          const bytes = row.bytes ?? new Blob([await row.file.arrayBuffer()], { type: "application/octet-stream" });
          const sha = row.sha ?? await imageDigest(await bytes.arrayBuffer());
          if (!mounted.current) return;
          // Retain a bounded snapshot for an uncertain upload retry; release bytes on success.
          updateRow(index, { bytes, sha, error: undefined });
          if (seen.has(sha)) {
            updateRow(index, { file: null, bytes: undefined, selected: false, omitted: true,
              error: "Duplicate image omitted from this cohort." }); continue;
          }
          const staged = await api.stageImage(batch, sha, bytes);
          seen.add(sha);
          updateRow(index, { staged, file: null, bytes: undefined, error: undefined });
        } catch (e) {
          updateRow(index, { error: message(e) });
          throw e; // Keep successful rows and all unattempted inputs; never silently shrink the cohort.
        }
      }
    } catch (e) { if (mounted.current) setError("Staging stopped. " + message(e)); }
    finally { running.current = false; if (mounted.current) setBusy(false); }
  }
  function accept(next: JobRecord, frozen: FrozenImageRequest) {
    const spec = next.spec, intended = frozen.request.spec;
    if (next.job_id !== frozen.jobId || next.request_id !== frozen.request.request_id || !("images" in spec) ||
        spec.method !== "B0" || spec.config_ref !== intended.config_ref || spec.reference_date !== intended.reference_date ||
        Object.keys(spec.images).sort().join() !== Object.keys(intended.images).sort().join() ||
        Object.keys(intended.images).some(id => spec.images[id].original_sha256 !== intended.images[id].original_sha256 ||
          spec.images[id].expected_revision !== intended.images[id].expected_revision)) throw new Error("image_job_identity_refused");
    if (mounted.current) setJob(next);
  }
  async function start() {
    if (disabled || running.current || (!pending && (!workerAvailable || !referenceDay(day)))) return;
    const selected = rows.filter(r => r.selected && !r.omitted);
    if (!pending && (!selected.length || selected.some(r => !r.staged))) return;
    running.current = true; setBusy(true); setError("");
    try {
      let frozen = pending;
      if (!frozen) {
        const current = await api.items(batch);
        if (!mounted.current) return;
        const images: ImageJobStart["spec"]["images"] = {};
        for (const row of selected) {
          const staged = row.staged!;
          const existing = current.find(item => item.item_id === staged.item_id);
          if (existing?.deleted || (existing && !existing.revision)) throw new Error("image_cohort_revision_refused");
          images[staged.item_id] = { schema_version: 1, original_sha256: staged.original_sha256,
            expected_revision: existing?.revision ?? null };
        }
        const request: ImageJobStart = { schema_version: 1, request_id: crypto.randomUUID(),
          spec: { schema_version: 1, method: "B0", config_ref: "receipt-image-local/1", reference_date: day, images } };
        frozen = { request, jobId: await imageDigest(new TextEncoder().encode(request.request_id).buffer) };
        // Set before POST: a lost acknowledgement must retry these exact bytes and identity.
        if (mounted.current) setPending(frozen);
      }
      if (!mounted.current) return;
      let next: JobRecord;
      try { next = await api.startImageJob(batch, frozen.request); }
      catch (e) {
        // The server looks up this intent before refusing an unavailable worker, before job creation.
        // Only this exact POST refusal proves non-admission; unknown ACKs and observed jobs stay frozen.
        if (!job && e instanceof ApiError && e.status === 503 && e.message === "image_worker_unavailable") {
          if (mounted.current) {
            setPending(null);
            setError("Local extraction is unavailable. No image job was created. Retry when available or clear this image workflow.");
          }
          return;
        }
        throw e;
      }
      accept(next, frozen);
      if (terminalImageJob(next)) await settled();
    } catch (e) { if (mounted.current) setError(message(e)); }
    finally { running.current = false; if (mounted.current) setBusy(false); }
  }
  async function refreshStatus(signal?: AbortSignal) {
    if (!pending || running.current || signal?.aborted) return;
    running.current = true; setBusy(true); setError("");
    try {
      const next = await api.imageJob(batch, pending.jobId, signal);
      if (signal?.aborted || !mounted.current) return;
      accept(next, pending);
      if (terminalImageJob(next)) await settled();
    } catch (e) { if (!signal?.aborted && mounted.current) setError(message(e)); }
    finally { running.current = false; if (mounted.current) setBusy(false); }
  }
  useEffect(() => {
    if (!job || terminalImageJob(job) || error) return;
    const controller = new AbortController();
    const timer = setTimeout(() => { void refreshStatus(controller.signal); }, 2000);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [job, pending, error]);
  const selected = rows.filter(r => r.selected && !r.omitted);
  const canClear = !pending || terminalImageJob(job);
  return <section className="card" aria-label="Receipt image import"><h2>Receipt images</h2>
    <p>Choose JPEG, PNG or HEIC images for this batch. Staging saves images only; it does not run OCR or create reviewed fields.</p>
    {!uploadAvailable && <p role="status">Image staging is unavailable on this server.</p>}
    <label>Receipt image files<input type="file" multiple accept=".jpg,.jpeg,.png,.heic,image/jpeg,image/png,image/heic"
      disabled={disabled || busy || !uploadAvailable || rows.length > 0 || !!pending}
      onChange={e => { choose(e.target.files); e.target.value = ""; }} /></label>
    {!!rows.length && <><ul>{rows.map((row, index) => <li key={index}>
      <label className="check"><input type="checkbox" aria-label={`Include ${row.name}`}
        checked={row.selected} disabled={disabled || busy || !!pending || !row.staged || row.omitted}
        onChange={e => updateRow(index, { selected: e.target.checked })} />{row.name}</label>
      <span>{row.staged ? "Staged · OCR not run" : row.omitted ? "Omitted duplicate" : "Not staged"}</span>
      {row.error && <p role="status">{row.error}</p>}</li>)}</ul>
      <button disabled={disabled || busy || !!pending || !uploadAvailable || !rows.some(r => r.file && !r.staged && !r.omitted)}
        onClick={() => void stage()}>Stage remaining images</button>
      <label>Extraction reference date<input type="date" value={day} disabled={disabled || busy || !!pending}
        onChange={e => setDay(e.target.value)} /></label>
      <p>{selected.length} selected images · local B0 extraction only · uncertain fields still require review.</p>
      {!workerAvailable && <p role="status">Local extraction is unavailable. A staged image is not an OCR result.</p>}
      <button disabled={disabled || busy || (!!job && !terminalImageJob(job)) || terminalImageJob(job) ||
        (!pending && (!workerAvailable || !referenceDay(day) || !selected.length || selected.some(r => !r.staged)))}
        onClick={() => void start()}>{pending ? "Retry frozen image job" : "Start selected images"}</button>
      <button disabled={disabled || busy || !canClear} onClick={() => { setRows([]); setPending(null); setJob(null); setDay(""); setError(""); }}>Clear image workflow</button>
      <p>Clearing removes this tab's selection; staged server images remain. No receipt content is saved in browser storage.</p>
    </>}
    {pending && <><p className="mono">Job {pending.jobId}</p>
      <p>Batch, cohort, revisions, date and request identity are frozen. Keep this tab open until its outcome is known. Retrying sends the same request.</p>
      <button disabled={disabled || busy} onClick={() => void refreshStatus()}>Read persisted image job status</button></>}
    {job && <div aria-label="Image job result"><p role="status">Image job: {job.state}</p>
      <ul>{Object.entries(job.items).map(([id, item]) => <li key={id}>{id}: {item.status}
        {item.reason ? ` · ${item.reason}` : ""}{item.result_revision ? ` · revision ${item.result_revision}` : ""}</li>)}</ul>
      {terminalImageJob(job) && <p>Only persisted successful items are available for review. Failed, stale, interrupted and unrun items remain listed here.</p>}</div>}
    {busy && <p role="status">Working with the fixed image workflow…</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}

export function App() {
  const [token, setToken] = useState("");
  const [api, setApi] = useState<HttpReviewApi | null>(null);
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [batch, setBatch] = useState(batchHash);
  const [batchInput, setBatchInput] = useState(batchHash);
  const [currency, setCurrency] = useState<Currency>("USD");
  const [items, setItems] = useState<ItemSummary[]>([]);
  const [detail, setDetail] = useState<ItemDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewLocked, setReviewLocked] = useState(false);
  const [imageLocked, setImageLocked] = useState(false);
  const locked = busy || reviewLocked || imageLocked;
  const [exportMode, setExportMode] = useState<ExportMode>("review");
  const [exportName, setExportName] = useState<ExportFile>("receipts.csv");
  const [notice, setNotice] = useState("");
  async function task(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function open(value: string, client = api) {
    if (!client || !/^[a-f0-9]{32}$/.test(value)) throw new Error("invalid_batch");
    const found = await client.items(value);
    const first = found.find(item => !item.deleted);
    const next = first ? await client.item(value, first.item_id) : null;
    setItems(found); setDetail(next); setBatch(value); setBatchInput(value);
    history.replaceState(null, "", `#batch=${value}`);
  }
  async function changed(next: ItemDetail) {
    setDetail(next); if (api) setItems(await api.items(batch));
  }
  async function connect() {
    const client = new HttpReviewApi(token, location.origin);
    const connected = await client.status();
    if (connected.contract !== "receipt-api/1") throw new Error("unsupported_contract");
    setApi(client); setStatus(connected); setToken("");
    if (batchInput) await open(batchInput, client);
  }
  async function importFile(file: File | undefined) {
    if (!api || !file) return;
    if (file.size > 8 * 1024 * 1024) { setError("Recognized bundle exceeds the 8 MiB viewer limit."); return; }
    await task(async () => {
      const value: unknown = JSON.parse(await file.text());
      const result = await api.importBundle(batch, value);
      await open(batch); setDetail(await api.item(batch, result.item_id));
    });
  }
  async function download() {
    if (!api) return;
    const blob = await api.exportFile(batch, exportMode, exportName);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = exportName;
    anchor.hidden = true; document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    setNotice("Export requested. Source-bearing JSONL is private review data.");
  }
  return <><header><span className="brand">R<span>/</span> Receipt Field Review</span><span className="local">Local workspace</span>
    {api && <button disabled={locked} onClick={() => { setApi(null); setStatus(null); setDetail(null); setItems([]); }}>Disconnect</button>}</header>
    <main>{!api ? <section className="connect card"><span className="eyebrow">Review with evidence</span>
      <h1>A clear view of every receipt field.</h1><p>Import receipts when the local server supports image staging and extraction, inspect recognized fields and source images, and save an auditable decision.</p>
      <form onSubmit={e => { e.preventDefault(); void task(connect); }}><label>Local capability<input type="password" value={token}
        autoComplete="off" maxLength={256} onChange={e => setToken(e.target.value)} /></label>
        <label>Existing batch ID (optional)<input value={batchInput} onChange={e => setBatchInput(e.target.value)} /></label>
        <button className="primary" disabled={locked || !token}>Connect to local API</button></form>
      <p className="muted">Capability and receipt content stay out of browser storage. Saved corrections live in the server journal. The URL fragment remembers only a batch identity.</p>
    </section> : <><section className="toolbar card"><div><span className="eyebrow">Recognized-bundle workspace</span>
      <h2>{batch ? "Batch ready for review" : "Start a batch"}</h2><p className="mono">{batch || "One currency · up to 100 receipt identities"}</p></div>
      <div className="toolbar-controls"><label>New batch currency<select value={currency} disabled={locked} onChange={e => setCurrency(e.target.value as Currency)}>
        {(status?.currencies ?? ["USD"]).map(code => <option key={code}>{code}</option>)}</select></label>
        <button disabled={locked} onClick={() => void task(async () => { if (api) await open((await api.createBatch(currency)).batch_id); })}>Create batch</button>
        <label>Open batch ID<input value={batchInput} onChange={e => setBatchInput(e.target.value)} /></label>
        <button disabled={locked || !/^[a-f0-9]{32}$/.test(batchInput)} onClick={() => void task(() => open(batchInput))}>Open batch</button></div>
      {batch && <div className="import-row"><label>Import recognized bundle<input type="file" accept=".json,application/json" disabled={locked}
        onChange={e => { const file = e.target.files?.[0]; e.target.value = ""; void importFile(file); }} /></label>
        <p className="muted">Validated JSON only. Image import uses the separate fixed-cohort workflow below.</p></div>}
    </section>
    {batch && <ImageImport key={batch} api={api} batch={batch} uploadAvailable={status?.capabilities.image_upload === true}
      workerAvailable={status?.capabilities.local_b0 === true} disabled={busy || reviewLocked} lock={setImageLocked}
      settled={() => open(batch)} />}
    {reviewLocked && <p className="muted">Finish, retry or discard your current edits before switching batches/items or exporting.</p>}
    {batch && <section className="batch-bar card"><label>Receipt<select value={detail?.review.item_id ?? ""} disabled={locked || !items.some(x => !x.deleted)}
      onChange={e => { const id = e.target.value; void task(async () => { if (api) setDetail(await api.item(batch, id)); }); }}>
      {!items.some(x => !x.deleted) && <option value="">No recognized items yet</option>}
      {items.map(item => <option key={item.item_id} value={item.item_id} disabled={item.deleted}>{item.item_id} · {item.deleted ? "deleted" : item.clean ? "resolved" : "review required"}</option>)}</select></label>
      <div className="exports"><label>Export mode<select value={exportMode} onChange={e => setExportMode(e.target.value as ExportMode)}><option value="review">Review (includes unresolved)</option><option value="clean">Clean (resolved only)</option></select></label>
        <label>Format<select value={exportName} onChange={e => setExportName(e.target.value as ExportFile)}>{["receipts.csv", "line_items.csv", "receipts.jsonl", "omitted.json"].map(name => <option key={name}>{name}</option>)}</select></label>
        <button disabled={locked} onClick={() => void task(download)}>Download export</button></div></section>}
    {detail ? <Review key={batch + "/" + detail.review.item_id} api={api} batch={batch} detail={detail} changed={changed} lock={setReviewLocked} disabled={imageLocked} /> :
      batch && <section className="empty card"><h2>Ready for a recognized bundle</h2><p>Import a validated bundle to see every field, check and source region. Conflicting arithmetic stays in review until explicitly resolved.</p></section>}
    </>}
    {busy && <p role="status">Working with the local journal…</p>}{error && <p role="alert" className="error global-message">{error}</p>}
    {notice && <p role="status" className="success global-message">{notice}</p>}
    <footer>Local review · Uncalibrated proposals require review · Operationally clean does not establish human Gold or measured accuracy</footer></main></>;
}
