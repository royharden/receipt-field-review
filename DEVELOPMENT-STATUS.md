# Development status

Paused on 2026-10-15. This is a local, partially implemented application. No hosted deployment,
public release, measured receipt accuracy or independent finished-application acceptance is claimed.
The implementation checkpoint before this documentation update is `604cac9a58d413c610576b8af1cc9f620ff950cd`.

## Finished implementation slices

- Four reusable Python foundations: Docio models and bounded TSV parsing; Fieldextract candidate
  selection and checks; Rulings durable JSONL decisions with CAS and historical retry; Evalkit
  generic statistics, paired group bootstrap, corpus/runner/reporting and binary calibration metrics.
- Receipt B0 extraction from supplied recognized pages: seven scalar fields, all line cells,
  printed adjustments, source evidence and Decimal/date/currency checks. Diagnostic scores do not
  authorize automatic acceptance.
- Private files/JSONL batch workflow, bounded to 100 identities and one currency policy. It retains
  unchanged machine proposals, projects review decisions, preserves them on unchanged-evidence reruns,
  and refuses stale or changed-evidence updates. Tombstones prevent resurrection.
- Recognized-bundle CLI: create, import, inspect, draft, apply and export. Stable saved drafts support
  exact retries. Review/clean CSV and full-source JSONL retain audit information and list omissions.
  Empty clean export writes an omission report and exits with a refusal.
- Durable recognized-item jobs: request-key idempotency, atomic progress, explicit stale/failed/
  unavailable outcomes and interruption recovery. B0 uses the local retained-document extractor;
  J1/V2 remain explicitly unavailable, without substitute results or invented cost.
- Canonical offline provider/ledger and screening components, with retained source provenance and
  licenses. These are not connected to live receipt methods.
- Pure API DTOs, generated JSON schema and TypeScript client contracts, stable decision-draft
  builder and a request-policy guard. These are contract code, not an HTTP implementation.

## Worked on / incomplete

The latest implementation checkpoint passed its recorded Python suite (216 top-level tests plus
15 subtests), three Node scaffold controls, shared/API schema parity, Ruff checks and the current
configuration/contract TypeScript check. These checks were not rerun for this documentation-only
pause. They establish tested component behavior on authored controls, not image OCR, HTTP security,
browser behavior, live-provider quality or application acceptance.

React/Vite/TypeScript scaffolding exists. No review viewer or runnable frontend build exists.
Native/API dependency compatibility and bounded public package metadata were investigated, but
Pillow/HEIF/FastAPI/Uvicorn/multipart/httpx were not installed into the application. No actual image
decoding, Tesseract image execution, HTTP listener, Docker stack or provider call was run.
A standalone synthetic recognized-bundle demo was planned but not implemented; no demo script or
example bundle is shipped. No uncommitted product-source changes were left at pause.

## Outstanding work

1. Ship a runnable, clearly synthetic recognized-bundle demo exercising normal review, clean refusal,
   restart, unchanged-source rerun and audited export through the existing public workflow.
2. Complete bounded dependency setup and actual PNG/JPEG/HEIC ingestion/OCR integration, with source
   artifacts, coordinates, failures and retained image handling verified end to end.
3. Implement the local HTTP adapter and worker ownership. Enforce request policies on actual streams
   and test transport, capability/origin checks, lifecycle, conflicts and failures in process.
4. Build the review UI: actual source overlays, all scalar/line/adjustment cells, keyboard review,
   visible conflicts/issues, persistent corrections, failure states and honest export omissions.
   Install real React type packages and validate the actual build/browser journey.
5. Integrate canonical J1/V2 model methods only after actual SDK, pricing, capabilities, cumulative
   budget reservation and bounded test authorization are established. Preserve every outcome and cost.
6. Obtain lawful real receipts and independent human labels; implement receipt-domain scorers and
   run required OCR and three-method comparisons. Keep the 100-phone-receipt 60-dev/40-held-out split
   and review-only behavior when the strict lower-95%-Wilson precision gate is not met.
7. Complete portability handoff and independent finished-app review. Python/native OCR/filesystem
   execution needs a local or separately hosted backend; a static viewer alone cannot provide it.
   No remote, Bolt import, database provisioning or deployment has been performed.

See [lessons](LESSONS.md), [limitations](docs/LIMITATIONS.md) and
[architecture](docs/architecture.md) before resuming. Resume requires an explicit instruction.
