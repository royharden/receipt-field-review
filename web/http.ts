import type { ApiStatus, AppendReceipt, BatchSummary, Currency, DecisionDraft, DraftInput,
  ExportFile, ExportMode, ItemDetail, ItemSummary, SourcePage } from "./contracts";

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
  if (error instanceof Error && error.message === "invalid_batch") return "Enter the complete 32-character batch identity.";
  if (error instanceof Error && error.message.startsWith("Exact loopback origin")) return "Enter a valid local capability (32–256 printable ASCII characters).";
  return "Request did not complete. Check the local server; a saved decision may be retried unchanged.";
}

/** Local review routes. No upload/job/model dispatch or persistent browser storage. */
export class HttpReviewApi {
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
  private async request(path: string, payload?: unknown, signal?: AbortSignal): Promise<Response> {
    const response = await this.fetcher(this.origin + path, {
      method: payload === undefined ? "GET" : "POST",
      headers: { "X-RFR-Token": this.token, ...(payload === undefined ? {} :
        { "Content-Type": "application/json" }) },
      body: payload === undefined ? undefined : JSON.stringify(payload),
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
