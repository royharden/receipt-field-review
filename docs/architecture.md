# Architecture boundary

Current implementation: four reusable foundations, a bounded decision journal/projection, an injected evaluator, a receipt-specific B0 adapter, a durable provided-bundle review/export workflow and CLI, durable recognized-item B0 jobs, a synthetic CLI demo, API DTO/schema/TypeScript contracts and a recognized-bundle FastAPI adapter. Image ingestion, actual native/model inference, image-upload jobs, listener/worker ownership and UI remain pending. See the [current inventory](../DEVELOPMENT-STATUS.md).

The demo orchestrates existing CLI entrypoints, `BatchStore`, decision drafts and `JobStore`; it owns
no parallel persistence or extraction implementation. Fresh CLI processes read saved decisions.
Explicit synthetic issue waivers remain auditable, and original machine values remain unchanged.
The pinned recognized fixture is product input; demo runtime imports no test helper or agent files.

The intended dependency direction is:

```text
UI -> local API -> receipt workflow -> shared module protocols
fieldextract -> docio
rulings and evalkit -> generic schemas/standard libraries
app adapters -> canonical external owner modules
```

Shared modules must not depend on app namespaces. Each export owns its models and protocol definitions; the app injects adapters. Provider/ledger and screening implementations come from their actual owning projects at verified commits with provenance and contract checks. The canonical S3 purpose-fixed offline provider/ledger and S6 screening closures now share one unchanged sibling package, `rfr.shared.execution`; exact commits, Git blob hashes and MIT notices are retained with actual isolated conformance controls. No live SDK is installed.

The bounded local workflow uses files plus append-only JSONL and a rebuildable in-memory projection, not a second authoritative application database. An adopted ledger may independently use SQLite. Private images/records/caches live in an ignored `data/` root and must not enter static viewer assets.

The static viewer will be transient synthetic-only. It cannot supply Python, OCR, human-labelled data or a live provider. Public serving requires a separately approved authentication/storage/job/budget design.

The batch mutex serializes app source-head updates and journal operations before the public journal lock. Immutable recognized bundles and an atomic manifest store source state; effective decisions are rebuilt from JSONL. Identical evidence/context preserves decisions across method reruns. Changed evidence/context, stale prior heads and old UI revisions fail closed. Local actor claims remain unverified for human-label exports.

The HTTP factory admits exact loopback Host/token and mutation Origin before reading a body.
A bounded JSON accumulator verifies real streamed bytes, message count, complete length and strict
JSON; the async transport supplies the receive deadline. File/journal operations run through the
existing thread-safe local workflow. Review detail excludes retained artifact bytes, fixed private
export routes retain audit sources, and unavailable images/jobs/live methods stay explicit.
Transport controls use the real ASGI app in process; no application listener or browser is implied.
