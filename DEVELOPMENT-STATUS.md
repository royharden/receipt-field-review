# Development status

Local recognized-bundle browser viewer added on 2026-10-15. This is a local, partially implemented application. No hosted deployment,
public release, measured receipt accuracy or independent finished-application acceptance is claimed.
The accepted local HTTP baseline is `0fc71bb31078e30746f4b718c8efe18d94333d18`.

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
  builder and a request-policy guard. The actual FastAPI adapter now applies these policies before
  routing/body reads, counts streamed bytes/messages and enforces a receive deadline. Typed local
  operations reuse the existing batch/journal/export implementation; no second persistence exists.
- A runnable synthetic recognized-bundle demo through the real CLI and durable workflow. It retains
  correction drafts, initial review exports and clean-export refusals, records explicit provisional
  decisions/issue waivers, and verifies restart plus a real local B0 rerun before audited CSV/JSONL
  export. The shipped fixture contains authored text/geometry/confidence and no original image.
- An optional local image-to-fields CLI through an explicitly installed English Tesseract engine.
  It retains original/normalized pixels and actual TSV, pins engine/model/configuration and grid
  identity, uses canonical Docio/B0/ReceiptBundle and registers through the existing review store.
  Bounded child failures and known batch refusal paths preserve existing data. Repeated identical
  machine evidence replays recorded corrections; changed evidence retains source conflicts.

## Worked on / incomplete

Before the demo, the implementation checkpoint passed its recorded Python suite (216 top-level tests plus
15 subtests), three Node scaffold controls, shared/API schema parity, Ruff checks and the current
configuration/contract TypeScript check. These checks were not rerun for this documentation-only
pause. They establish tested component behavior on authored controls, not image OCR, HTTP security,
browser behavior, live-provider quality or application acceptance.

The demo continuation's first two combined runs retained 2/1 five-second process-start barrier
failures respectively, despite isolated passes. A later independent default, uninstrumented run
of that exact demo candidate passed 479 ordinary tests plus 15 successful subreports with unchanged
native deadlines. The local recognized-bundle slice and that current combined gate were accepted
with notes. The earlier intermittent failures remain unexplained; no causal fix or stable timing
reliability is claimed. Whole-app acceptance remains outstanding. The exact final HTTP candidate later passed an independent default combined run: 516 ordinary tests,
531 suite-reported calls including subreports, zero failures/errors/skips, and six independent real
ASGI checks. That local HTTP supplement was accepted with notes. The new viewer requires its own
independent disposition; no unchanged combined rerun is counted for it.

FastAPI, Starlette, Uvicorn and httpx are now installed through the portable official-PyPI lock.
The actual wheel build succeeds and retains required schemas plus vendored license notices.
In-process TestClient and direct ASGI controls exercise HTTP admission, bounded fragmented bodies,
timeout/disconnect refusal, correction/retry/restart, stale conflicts and private exports. The
Starlette httpx-backend deprecation warning is retained. Windows event-loop control socket pairs
are allowed in the test harness; application socket connections remain denied. A later recognized-bundle viewer continuation exercised a real loopback Uvicorn listener and Chromium
against authored data; original images, actual OCR and live providers remain unexercised.

The React/TypeScript/Vite viewer now has an actual root build and same-origin local Python launcher.
All scalar/line/adjustment cells, recognized-text region preview, explicit decisions/waivers,
private exports, saved-draft retry, unsaved-navigation locks and stale-state errors are implemented.
A bounded immutable public shell is separated from capability-protected receipt APIs. New React
type packages are pinned. Targeted repair setup used a separate installed runtime; the lock-only
command rewrote the original node_modules hidden lock metadata. Retained package code files and
Python/prior viewer runtime hashes remain unchanged; the setup metadata delta is recorded separately.
The optional image-staging command now decodes PNG/JPEG/HEIC locally; a separate installed-Tesseract
CLI joins images through OCR/B0 and review. HTTP image jobs and original-image UI integration remain pending. The demo still uses authored geometry and
confidence; explicit provisional waivers do not establish verified receipt arithmetic or human Gold.

The viewer continuation passed the actual TypeScript/Vite build, six client controls, three frontend
configuration controls and 87 API controls. Authored Windows/Chromium browser controls exercised
recognized import, keyboard correction, two-tab stale refusal with retained text, 17 remaining
individual field decisions and nine explicit issue waivers. Final server restart replay preserved
the corrected value and operationally resolved state. The in-app browser delivered actual CSV and
JSONL files; inspected JSONL retained all 18 original machine fields, artifact bytes and provisional
labels. CLI-browser download cancellations and a download-event timeout during the bounded server
window remain retained failures; their cause is not claimed resolved by alternate-browser success.
This is author verification of a narrow recognized-only journey, pending independent viewer review.

Independent viewer review found that Ctrl+Enter could bypass the disabled normal-save control
while an exact draft was pending. A new stale draft could then turn off retry availability; canonical
CAS still protected the saved decision. That viewer candidate was not accepted. The targeted repair
guards all save entries, maps the shortcut to the retained exact retry and shows the matching hint.
Actual React/synthetic-DOM controls use a real canonical commit with an explicit test-only lost
acknowledgement, plus stale/busy/cancel/replay cases. These checks do not supply independent native
UI/keyboard, browser response-loss or OS-save evidence. Fresh review and remaining native gates are
still required; earlier author browser files and accepted HTTP evidence remain separate editions.
Independent review later qualified the bounded pending-policy construction repair and closed that
defect only. Native UI/real HTTP committed-response-loss/native save acceptance remains blocked.

A separate optional image-staging command now retains exact originals, normalized RGB PNGs and a
closed manifest under private content-addressed directories. Actual Windows Pillow/HEIF codec
controls use authored pixels, including all eight JPEG orientations and HEIC container orientation.
Limits, malformed/multipage refusal, metadata stripping, hash binding and no-overwrite staging are
checked. A failed HEIC orientation fixture was corrected at the test writer boundary; failed runs
are retained. This does not run native OCR, import a receipt, provide a hostile upload sandbox or
resolve any native browser acceptance gate. Optional Linux CI is configured, not remotely executed.

The new native bridge's authored Windows functional control runs the public CLI on generated pixels,
then exercises correction, exact decision retry, another actual OCR import, reopen and CSV/JSONL
export. It retains measured word boxes/confidences and provisional review audit state. The first
native version probe timed out before OCR; later focused controls passed, with no cause or stable
startup-reliability claim. An earlier broad Python run recorded failures before its wrapper timed
out; that combined gate remains unresolved. Focused checks and native functional execution are
not independent finished-application acceptance, real-receipt accuracy or a real-dev engine comparison.
The app-local adapter is not yet a separately published reusable native Docio export closure.

The subsequent joined core/CLI/adapter check recorded 137 ordinary passes, 15 successful subtests
and two failures: a native version-probe timeout and the unchanged two-process review test's
20-second child timeout. Removing the extra 10-second probe cap keeps one overall 30-second
native budget; regression controls verify slow startup and no OCR dispatch after budget exhaustion.
A fresh frozen environment and exact moved source then recorded four targeted passes and one
native CLI failure. Both engine commands exited successfully and were reaped, but the full native
operation exhausted its total budget before TSV assembly. The two-process case passed only in
that moved context. Neither result resolves the earlier failures or establishes their cause.
Static/schema checks and wheel build/install/import pass; native timing, the joined gate and
independent acceptance remain open. No timeout was widened and no failed run was discarded.

## Outstanding work

1. Qualify preprocessing and native engine selection on lawful real dev data, and connect the local
   native CLI boundary to durable image jobs. The basic actual image/OCR/B0/review CLI join is now
   implemented; real-data quality, reusable native-adapter export and broad acceptance remain open.
2. Add actual listener/worker lifecycle and HTTP job integration. The recognized-bundle adapter
   covers in-process request policy and durable review/export. Authenticated normalized-source reads
   now bind existing local pixels to the current item revision/Docio grid; native upload/job paths remain absent.
3. Qualify the new normalized-image fetch/selected-region overlay in the actual browser and complete
   native/image job integration. The source preview now joins existing authenticated pixels with
   revision/grid checks and text fallback; static unsaved demo mode and full native/held-out/browser
   matrix remain pending. Authored component events do not establish native image decoding or save.
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
