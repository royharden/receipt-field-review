// Initial receipt-api/1 viewer contract. Server schemas remain normative; this file grants no effects.
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Method = "B0" | "J1" | "V2";
export type Currency = "USD" | "EUR" | "GBP" | "CAD" | "AUD" | "JPY" | "KWD";
export type Scalar = "merchant_name" | "date" | "currency" | "subtotal" | "tax" | "total" | "payment_method";
export type LineCell = "description" | "quantity" | "unit_price" | "amount";
export type Action = "correct" | "confirm" | "waive_absent" | "reopen";
export interface Wire { schema_version: 1 }
export interface Box extends Wire { units: "px"; x0: number; y0: number; x1: number; y1: number }
export interface Evidence extends Wire {
  document_id: string; original_content_sha256: string; raw_source_revision: string;
  page_id: string; page_index: number; page_sha256: string; grid_policy_id: string;
  width_px: number; height_px: number; evidence_artifact_sha256: string;
  bbox_px: Box | null; word_ids: string[] | null; line_ids: string[] | null;
  excerpt_sha256: string | null; transform_ref: string | null;
}
export type EvidenceSource = (Wire & {kind: "document"; evidence: Evidence}) |
  (Wire & {kind: "extension"; profile: string; evidence_id: string; payload: {[key: string]: Json}});
export interface MachineField extends Wire {
  field_id: string; value: Json; confidence: number | null; source: EvidenceSource | null;
  method: string; status: "proposed" | "absent" | "abstained" | "needs_review" | "human_effective";
  proposal: Json; human_provenance_ref: string | null; hard_flags: string[]; issues: string[];
  components: Wire & {selector_probability: number | null; verifier_probability: number | null;
    native_quality_multiplier: number | null; native_quality_policy: string | null};
  score_version: string; threshold_version: string;
}
export interface Label extends Wire {
  namespace: string; item_id: string; field_id: string; row_key: string | null;
  presence: "present" | "absent" | "unlabelled"; value: Json;
  label_source: "human" | "agent_provisional" | "unverified_human" | "unlabelled";
  label_provenance_ref: string | null; event_id: string | null; head_event_id: string;
  source_revision: string | null; evidence_revision: string | null;
  state: "effective" | "waived_absent" | "needs_review";
}
export interface ReviewField extends Wire {
  machine: MachineField; effective_value: Json; corrected: boolean; decision_old_value: Json;
  review_state: "correct" | "confirm" | "waive_absent" | "needs_review" | "proposed" | "absent";
  head_event_id: string | null; effective_event_id: string | null; conflict: string | null;
  label: Label | null;
}
export interface Word extends Wire {
  stable_id: string; text: string; bbox_px: Box | null; ocr_confidence: number | null;
  geometry_provenance: "measured_ocr" | "native" | "model_claimed" | "none";
  source_engine: string; source_engine_version: string;
}
export interface SourceLine extends Word { ordered_child_ids: string[] }
export interface SourcePage extends Wire {
  document_id: string; raw_source_revision: string; page_id: string; page_index: number;
  width_px: number; height_px: number; page_sha256: string; grid_policy_id: string;
  words: Word[]; lines: SourceLine[]; blocks: SourceLine[];
  source_kind: "image" | "pdf" | "native_text" | "screenshot"; processing_ref: string;
}
export interface SourceDocument extends Wire {
  document_id: string; original_content_sha256: string; raw_source_revision: string;
  source_kind: SourcePage["source_kind"]; pages: SourcePage[];
  provenance: Wire & {producer: string; version: string; config_sha256: string;
    source_grid_profile: string; refs: string[]};
}
export interface CurrencyPolicy extends Wire {
  code: Currency; decimal_separator: "." | ","; group_separator: "." | "," | " " | null;
  version: "receipt-currency/1";
}
export interface Check extends Wire {
  check_id: string; status: "pass" | "fail" | "not_checkable"; field_ids: string[]; reason: string | null;
}
export interface Receipt extends Wire {
  receipt_id: string; document_id: string; raw_source_revision: string; artifact_sha256: string;
  context: Wire & {currency: CurrencyPolicy; reference_date: string | null; policy_version: "receipt-checks/1"};
  fields: Record<Scalar, MachineField>;
  line_items: (Wire & {row_key: string; cells: Record<LineCell, MachineField>})[];
  adjustments: (Wire & {adjustment_id: string; kind: "tip" | "service" | "discount";
    stage: "before_subtotal" | "after_subtotal" | "unknown"; amount: MachineField})[];
  checks: Check[];
}
export interface Generation extends Wire {
  kind: "scalar"; profile: string; source_sha256: string;
  raw_source_revision: string; evidence_revision: string | null;
}
export interface ItemReview extends Wire {
  item_id: string; revision: string; generation: Generation; receipt: Receipt;
  document: SourceDocument; fields: Record<string, ReviewField>; checks: Check[];
  issue_ids: string[]; unresolved_issues: string[]; unfinished_fields: string[];
  clean: boolean; journal_status: string; label_authority: string;
}
export interface ItemDetail extends Wire { review: ItemReview; image_available: boolean }
export interface DraftInput {
  field_id: string; action: Action; value?: string | null; expected_item_revision: string;
  expected_prior_event_id: string | null; actor: string;
  actor_kind?: "agent_provisional" | "human_claimed"; actor_ref?: string | null;
  event_id?: string | null; reason: string; waive_issues?: string[]; issue_reason?: string | null;
}
export interface DecisionDraft { expected_item_revision: string; intent: {[key: string]: Json} }
export interface AppendReceipt extends Wire {
  event_id: string; sequence: number; intent_sha256: string;
  outcome: "appended" | "exact_retry"; historical: boolean; current_generation_authority: false;
}
export interface JobSpec extends Wire {
  method: Method; source_revisions: Record<string, string>; config_ref: "receipt-local/1";
}
export interface JobItem extends Wire {
  status: "queued" | "running" | "ok" | "error" | "stale" | "unavailable" | "not_run" | "unknown_interrupted";
  result_revision: string | null; reason: string | null;
}
export interface JobRecord extends Wire {
  job_id: string; request_id: string; spec: JobSpec; execution_config_sha256: string;
  state: "pending" | "running" | "complete" | "partial" | "failed" | "interrupted";
  items: Record<string, JobItem>; started_at: string | null; ended_at: string | null;
  execution_origin: "local_rules" | "not_run"; model_cost_usd: null;
  model_cost_status: "not_applicable" | "not_run";
}
export interface ItemSummary extends Wire {
  item_id: string; revision: string | null; deleted: boolean; clean: boolean;
  unfinished_fields: string[]; unresolved_issues: string[];
}
export interface BatchSummary extends Wire { batch_id: string; currency: Currency; item_count: number }
export interface BatchView extends BatchSummary { items: ItemSummary[]; jobs: JobRecord[] }
export interface ApiStatus extends Wire {
  contract: "receipt-api/1"; mode: "local" | "synthetic_demo"; stage: string;
  currencies: Currency[];
  capabilities: Wire & {recognized_import: boolean; image_upload: boolean; source_images: boolean;
    review_persistence: boolean; local_b0: boolean; jev: boolean; vision: boolean};
}
export type ExportMode = "review" | "clean";
export type ExportFile = "receipts.csv" | "line_items.csv" | "receipts.jsonl" | "omitted.json";
export interface ReviewApi {
  readonly readOnly: boolean;
  status(): Promise<ApiStatus>;
  batches(): Promise<BatchSummary[]>;
  createBatch(currency: Currency): Promise<BatchSummary>;
  batch(batch: string): Promise<BatchView>;
  item(batch: string, item: string): Promise<ItemDetail>;
  image(batch: string, item: string, revision: string, page: SourcePage, signal?: AbortSignal): Promise<Blob>;
  draft(batch: string, item: string, input: DraftInput): Promise<DecisionDraft>;
  apply(batch: string, draft: DecisionDraft): Promise<AppendReceipt>;
  startJob(batch: string, request: string, spec: JobSpec): Promise<JobRecord>;
  job(batch: string, job: string): Promise<JobRecord>;
  exportFile(batch: string, mode: ExportMode, format: ExportFile): Promise<Blob>;
  uploadImage(batch: string, file: File): Promise<ItemSummary>;
}
