import type { ApiStatus, AppendReceipt, BatchSummary, Currency, DecisionDraft, DraftInput,
  ExportFile, ExportMode, ImageJobsApi, ImageJobStart, ItemDetail, ItemSummary, JobRecord,
  SourcePage, StagedImage } from "./contracts";

export const IMAGE_LIMIT = 20 * 1024 * 1024;
const digest = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const imageBatch = (batch: string) => { if (!/^[a-f0-9]{32}$/.test(batch)) throw new Error("invalid_batch"); };
export async function imageDigest(bytes: ArrayBuffer): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
}

function imageJob(value: unknown, jobId: string, request?: ImageJobStart): JobRecord {
  const fail = () => { throw new Error("image_job_identity_refused"); };
  if (!record(value) || value.schema_version !== 1 || value.job_id !== jobId ||
      typeof value.request_id !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value.request_id) ||
      !["pending", "running", "complete", "partial", "failed", "interrupted"].includes(String(value.state)) ||
      !record(value.spec) || !record(value.spec.images) || !record(value.items) ||
      value.spec.schema_version !== 1 || value.spec.method !== "B0" || value.spec.config_ref !== "receipt-image-local/1" ||
      typeof value.spec.reference_date !== "string" ||
      !["local_image_pipeline", "not_run"].includes(String(value.execution_origin)) || value.model_cost_usd !== null ||
      !["not_applicable", "not_run"].includes(String(value.model_cost_status))) return fail();
  const spec = value.spec, images = value.spec.images, items = value.items;
  const ids = Object.keys(images).sort();
  if (!ids.length || ids.length > 100 || ids.join() !== Object.keys(items).sort().join()) return fail();
  for (const id of ids) {
    const source = images[id], progress = items[id];
    if (!record(source) || !record(progress) || !digest(source.original_sha256) ||
        id !== "receipt-image:" + source.original_sha256 || source.schema_version !== 1 ||
        (source.expected_revision !== null && !digest(source.expected_revision)) || progress.schema_version !== 1 ||
        !["queued", "running", "ok", "error", "stale", "unavailable", "not_run", "unknown_interrupted"].includes(String(progress.status)) ||
        (progress.result_revision !== null && !digest(progress.result_revision)) ||
        (progress.status === "ok" && !digest(progress.result_revision)) ||
        (progress.status === "ok" && (value.execution_origin !== "local_image_pipeline" || value.model_cost_status !== "not_applicable")) ||
        (progress.reason !== null && typeof progress.reason !== "string") ||
        (value.state === "complete" && progress.status !== "ok")) return fail();
  }
  if (request && (value.request_id !== request.request_id || spec.reference_date !== request.spec.reference_date ||
      ids.join() !== Object.keys(request.spec.images).sort().join() || ids.some(id => {
        const source = images[id];
        return !record(source) || source.original_sha256 !== request.spec.images[id].original_sha256 ||
          source.expected_revision !== request.spec.images[id].expected_revision;
      }))) return fail();
  return value as unknown as JobRecord;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, code: string) {
    super(code); this.name = "ApiError"; this.status = status;
  }
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.message === "clean_export_empty") return "No resolved receipts to export. Review the unfinished fields and issues, or download the omission report.";
    if (error.status === 409) return `${error.message}. State may have changed. Reload before editing; your text is retained.`;
    return `${error.message} (HTTP ${error.status})`;
  }
  if (error instanceof SyntaxError) return "The selected file is not valid JSON. No bundle was submitted.";
  if (error instanceof Error && error.message === "image_stage_identity_refused") return "The server staging response did not match this image. No OCR success is established. Retry the same image.";
  if (error instanceof Error && error.message === "image_job_identity_refused") return "The job response did not match its frozen identity and cohort. Keep this tab open and read status or retry the same request.";
  if (error instanceof Error && error.message === "invalid_batch") return "Enter the complete 32-character batch identity.";
  if (error instanceof Error && error.message.startsWith("Exact loopback origin")) return "Enter a valid local capability (32–256 printable ASCII characters).";
  return "Request did not complete. Check the local server; a saved decision may be retried unchanged.";
}

/** Local capability routes; image jobs are B0 only, never a model/provider fallback. */
export class HttpReviewApi implements ImageJobsApi {
  private readonly token: string;
  private readonly origin: string;
  private readonly fetcher: typeof fetch;
  constructor(token: string, origin: string, fetcher: typeof fetch = globalThis.fetch) {
    const url = new URL(origin);
    if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname) ||
        url.origin !== origin || !/^[\x21-\x7e]{32,256}$/.test(token)) {
      throw new Error("Exact loopback origin and a 32–256 character ASCII capability required");
    }
    // Browser fetch requires the Window receiver; a method call on this client is illegal.
    this.token = token; this.origin = origin; this.fetcher = fetcher.bind(globalThis);
  }
  private async request(path: string, payload?: unknown, signal?: AbortSignal, upload?: Blob): Promise<Response> {
    const response = await this.fetcher(this.origin + path, {
      method: upload !== undefined ? "PUT" : payload === undefined ? "GET" : "POST",
      headers: { "X-RFR-Token": this.token, ...(upload !== undefined ? { "Content-Type": "application/octet-stream" } : payload === undefined ? {} :
        { "Content-Type": "application/json" }) },
      body: upload !== undefined ? upload : payload === undefined ? undefined : JSON.stringify(payload),
      credentials: "omit", cache: "no-store", redirect: "error", mode: "same-origin",
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000),
    });
    if (!response.ok) {
      let code = "request_refused";
      try {
        const value: unknown = await response.json();
        if (value && typeof value === "object" && "error" in value &&
            typeof value.error === "string" && /^[a-z0-9_]{1,80}$/.test(value.error)) code = value.error;
      } catch { /* Body diagnostics never become display text. */ }
      throw new ApiError(response.status, code);
    }
    return response;
  }
  private itemPath(batch: string, item: string) {
    return `/api/batches/${encodeURIComponent(batch)}/items/${encodeURIComponent(item)}`;
  }
  async status(): Promise<ApiStatus> { return (await this.request("/api/status")).json(); }
  async createBatch(currency: Currency): Promise<BatchSummary> {
    return (await this.request("/api/batches", { currency: { code: currency } })).json();
  }
  async items(batch: string): Promise<ItemSummary[]> {
    return (await this.request(`/api/batches/${encodeURIComponent(batch)}/items`)).json();
  }
  async item(batch: string, item: string): Promise<ItemDetail> {
    return (await this.request(this.itemPath(batch, item))).json();
  }
  async image(batch: string, item: string, revision: string, page: SourcePage, signal?: AbortSignal): Promise<Blob> {
    if (!/^[a-f0-9]{64}$/.test(revision) || !/^[a-f0-9]{64}$/.test(page.page_sha256) ||
        !Number.isSafeInteger(page.width_px) || !Number.isSafeInteger(page.height_px) ||
        page.width_px < 1 || page.height_px < 1 || page.width_px * page.height_px > 25_000_000) {
      throw new Error("source_image_identity_refused");
    }
    const response = await this.request(this.itemPath(batch, item) + `/page?revision=${revision}`, undefined, signal);
    if (response.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "image/png" ||
        response.headers.get("X-RFR-Item-Revision") !== revision ||
        response.headers.get("X-RFR-Page-SHA256") !== page.page_sha256) {
      throw new Error("source_image_identity_refused");
    }
    const blob = await response.blob();
    if (blob.size < 33 || blob.size > 80 * 1024 * 1024) throw new Error("source_image_identity_refused");
    const header = new Uint8Array(await blob.slice(0, 24).arrayBuffer());
    const dimensions = new DataView(header.buffer, header.byteOffset, header.byteLength);
    // The server verifies the complete normalized PNG and canonical RGBA grid. Here we bind
    // that response to the requested view before creating a browser-local object URL.
    if (![137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82].every((v, i) => header[i] === v) ||
        dimensions.getUint32(16) !== page.width_px || dimensions.getUint32(20) !== page.height_px) {
      throw new Error("source_image_identity_refused");
    }
    return blob;
  }
  async importBundle(batch: string, bundle: unknown): Promise<{ item_id: string; revision: string }> {
    return (await this.request(`/api/batches/${encodeURIComponent(batch)}/recognized`, { bundle })).json();
  }
  async stageImage(batch: string, originalSha256: string, bytes: Blob): Promise<StagedImage> {
    imageBatch(batch);
    if (!digest(originalSha256) || bytes.size < 1 || bytes.size > IMAGE_LIMIT) throw new Error("image_stage_identity_refused");
    const value: unknown = await (await this.request(`/api/batches/${batch}/images/${originalSha256}`, undefined, undefined, bytes)).json();
    if (!record(value) || value.schema_version !== 1 || value.item_id !== "receipt-image:" + originalSha256 ||
        value.original_sha256 !== originalSha256 || value.original_bytes !== bytes.size || value.ocr_executed !== false ||
        !["PNG", "JPEG", "HEIC"].includes(String(value.original_format)) || !digest(value.normalized_png_sha256) ||
        typeof value.width !== "number" || !Number.isSafeInteger(value.width) || value.width < 1 ||
        typeof value.height !== "number" || !Number.isSafeInteger(value.height) || value.height < 1 ||
        value.width * value.height > 25_000_000) throw new Error("image_stage_identity_refused");
    return value as unknown as StagedImage;
  }
  async startImageJob(batch: string, input: ImageJobStart): Promise<JobRecord> {
    imageBatch(batch);
    const jobId = await imageDigest(new TextEncoder().encode(input.request_id).buffer);
    return imageJob(await (await this.request(`/api/batches/${batch}/image-jobs`, input)).json(), jobId, input);
  }
  async imageJob(batch: string, job: string, signal?: AbortSignal): Promise<JobRecord> {
    imageBatch(batch);
    if (!digest(job)) throw new Error("image_job_identity_refused");
    const value: unknown = await (await this.request(`/api/batches/${batch}/image-jobs/${job}`, undefined, signal)).json();
    const validated = imageJob(value, job);
    if (await imageDigest(new TextEncoder().encode(validated.request_id).buffer) !== job) throw new Error("image_job_identity_refused");
    return validated;
  }
  async draft(batch: string, item: string, input: DraftInput): Promise<DecisionDraft> {
    return (await this.request(this.itemPath(batch, item) + "/draft", input)).json();
  }
  async apply(batch: string, item: string, draft: DecisionDraft): Promise<AppendReceipt> {
    return (await this.request(this.itemPath(batch, item) + "/decisions", draft)).json();
  }
  async exportFile(batch: string, mode: ExportMode, name: ExportFile): Promise<Blob> {
    return (await this.request(`/api/batches/${encodeURIComponent(batch)}/exports/${mode}/${name}`)).blob();
  }
}
