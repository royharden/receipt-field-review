# Architecture boundary

Current implementation: four reusable foundations, a bounded decision journal/projection, an injected evaluator, a receipt-specific B0 adapter, a durable provided-bundle review/export workflow and CLI, durable recognized-item B0 jobs, a synthetic CLI demo, API DTO/schema/TypeScript contracts and a recognized-bundle FastAPI adapter. Image ingestion, actual native/model inference, image-upload jobs, worker ownership and original-image UI remain pending; the recognized-bundle viewer and loopback launcher are implemented. See the [current inventory](../DEVELOPMENT-STATUS.md).

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

The local viewer is compiled from root React/TypeScript/Vite sources. A bounded startup snapshot
serves only index and hashed JS/CSS assets publicly under the exact Host policy. Private roots cannot
overlap that snapshot; receipt APIs remain token-protected. The browser uses same-origin requests,
retains capability/unsaved drafts only in memory, and uses canonical server decisions/exports without
a parallel browser store. Its text/geometry preview is distinct from an original-image overlay.

The browser mount is isolated in bootstrap.tsx so tests can render the actual Review component
without auto-mounting the app or inventing a parallel state controller. The consumer test port exposes
only draft/apply/item; production uses HttpReviewApi. Synthetic DOM events and an explicit after-commit
acknowledgement fault cross a real canonical service/journal boundary, without claiming live HTTP or
native browser behavior. A retained pending intent is the only allowed retry payload.

## Optional image staging boundary

`rfr.ingest` is app-local preliminary image staging, separate from canonical recognized Docio wires
and the authoritative BatchStore/journal. It keeps original.bin, normalized page.png and a final
closed image manifest under a content-addressed private folder. There is no OCR dispatch, receipt
batch creation, HTTP upload or UI source endpoint in this boundary. Future OCR must bind its
source-page grid to the normalized PNG digest/dimensions and keep the original identity separately.

Optional pinned Pillow/HEIF codecs enforce encoded/header/delivered/frame/output limits. EXIF
normalization records forward/inverse pixel-boundary matrices. HEIC starts with libheif-delivered
pixels after container transforms, with no asserted affine back to encoded container coordinates.
Fresh RGB output strips copied metadata and uses white alpha compositing; original metadata stays
private. Partial/changed output fails closed. Native codec sandbox/deadline/worker lifecycle, image
job/storage integration and source overlays remain required integration work.
