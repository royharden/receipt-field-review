# Development status

Local recognized-bundle demo added on 2026-10-15. This is a local, partially implemented application. No hosted deployment,
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
- A runnable synthetic recognized-bundle demo through the real CLI and durable workflow. It retains
  correction drafts, initial review exports and clean-export refusals, records explicit provisional
  decisions/issue waivers, and verifies restart plus a real local B0 rerun before audited CSV/JSONL
  export. The shipped fixture contains authored text/geometry/confidence and no original image.

## Worked on / incomplete

Before the demo, the implementation checkpoint passed its recorded Python suite (216 top-level tests plus
15 subtests), three Node scaffold controls, shared/API schema parity, Ruff checks and the current
configuration/contract TypeScript check. These checks were not rerun for this documentation-only
pause. They establish tested component behavior on authored controls, not image OCR, HTTP security,
browser behavior, live-provider quality or application acceptance.

The demo continuation's first combined run passed 477 tests and 15 subtests, with two existing
rulings process tests failing their five-second startup barriers. A fresh focused run of all six
process controls passed without changing source or deadlines. A second combined run passed 478
tests and 15 subtests, but the same-head CAS startup barrier failed again. Its cause remains
unresolved and blocks acceptance; no deadline was relaxed. All six new demo controls passed in
both combined runs, including a detached product copy, fixture-tamper refusal, restart/rerun and
malformed update preservation. Lint/format, shared/API schema parity, Node scaffold controls and
TypeScript checks passed. A wholly green combined run is not claimed. This evidence supports the
synthetic local slice, not finished-app acceptance.

React/Vite/TypeScript scaffolding exists. No review viewer or runnable frontend build exists.
Native/API dependency compatibility and bounded public package metadata were investigated, but
Pillow/HEIF/FastAPI/Uvicorn/multipart/httpx were not installed into the application. No actual image
decoding, Tesseract image execution, HTTP listener, Docker stack or provider call was run.
`scripts/demo.py` now runs the shipped recognized bundle without keys or inference. Its output must
be a new owner-private directory; an interrupted run preserves partial files without a completion
marker. Synthetic arithmetic waivers illustrate operational review, not verified numbers or human
Gold. The previous pause left no uncommitted source changes; the demo continues from that checkpoint.

## Outstanding work

1. Complete bounded dependency setup and actual PNG/JPEG/HEIC ingestion/OCR integration, with source
   artifacts, coordinates, failures and retained image handling verified end to end.
2. Implement the local HTTP adapter and worker ownership. Enforce request policies on actual streams
   and test transport, capability/origin checks, lifecycle, conflicts and failures in process.
3. Build the review UI: actual source overlays, all scalar/line/adjustment cells, keyboard review,
   visible conflicts/issues, persistent corrections, failure states and honest export omissions.
   Install real React type packages and validate the actual build/browser journey.
4. Integrate canonical J1/V2 model methods only after actual SDK, pricing, capabilities, cumulative
   budget reservation and bounded test authorization are established. Preserve every outcome and cost.
5. Obtain lawful real receipts and independent human labels; implement receipt-domain scorers and
   run required OCR and three-method comparisons. Keep the 100-phone-receipt 60-dev/40-held-out split
   and review-only behavior when the strict lower-95%-Wilson precision gate is not met.
6. Complete remaining portability verification and independent finished-app review. The initial
   [handoff inventory](BOLT-HANDOFF.md) is supplied. Python/native OCR/filesystem
   execution needs a local or separately hosted backend; a static viewer alone cannot provide it.
   No remote, Bolt import, database provisioning or deployment has been performed.

See [lessons](LESSONS.md), [limitations](docs/LIMITATIONS.md) and
[architecture](docs/architecture.md) before extending the next integration slice.
