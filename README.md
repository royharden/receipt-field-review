# Receipt Field Review

Receipt Field Review proposes fixed receipt scalar/line-cell fields from supplied recognized pages, preserves review decisions across unchanged-evidence reruns, and exports private CSV/JSONL with field audit metadata. It uses four reusable foundations, a durable decision journal and canonical offline execution components. A local recognized-bundle HTTP adapter and browser review viewer are implemented. Image ingestion, actual native/model inference, HTTP jobs and original-image overlays remain under construction.

## Keyless local demo

From the repository root with Python 3.12 and uv:

```text
uv sync --frozen
mkdir data
uv run --no-sync python scripts/demo.py --mode mock --out data/recognized-demo
```

The demo itself uses the installed environment without network, keys, image decoders or provider
SDKs. It imports the shipped [synthetic recognized bundle](examples/README.md), records a merchant
correction, proves clean export still refuses unresolved fields, explicitly reviews every field and
waives the deliberately conflicting arithmetic for this synthetic demonstration. Fresh CLI processes
and an actual local B0 rerun replay the saved correction. CSV, line-item CSV and complete JSONL exports
retain original machine evidence/confidence and provisional decision audit metadata.

A successful command prints `synthetic_recognized_bundle_demo_complete` and the private clean-export
path. `data/recognized-demo/DEMO.json` records the fixture hash, refusal reports, explicit issue waivers,
rerun outcome and file digests. Review the initial `review_export` and `clean_refusals` entries beside
the final export: clean means operationally reviewed, including explicit waivers; arithmetic issues
are never silently fixed. All decisions are `agent_provisional`, with no human Gold claim.

Output must be a new directory under an existing owner-controlled local parent. Repeated runs refuse
to overwrite it; choose a new name. Interrupted output is preserved without a success marker. After
the demo exits, use its `data_root`, `batch_id` and `item_id` with the CLI below to inspect durable state.
Only the pinned authored fixture is used; arbitrary receipts belong in the validated bundle CLI.
The fixture has no original image: its text, geometry and confidence are authored controls, with
provenance documented beside it. This demonstrates local workflow construction, not image OCR,
measured extraction quality or finished-app acceptance.

See [development status](DEVELOPMENT-STATUS.md), [lessons](LESSONS.md) and
[the portability handoff](BOLT-HANDOFF.md) for completed behavior and remaining integration work.

## Recognized-bundle review CLI

Use Python3.12 in the installed environment. `python -m rfr.cli --help` exposes batch creation,
bounded recognized-bundle import, list/detail, stable decision drafts, exact draft application and
exports. It accepts a validated `rfr.pipeline.models.ReceiptBundle`; it does not read images or invent OCR.

```text
python -m rfr.cli --root <existing-private-batch-directory> new --currency USD
python -m rfr.cli --root <directory> import-bundle --batch <batch-id> --bundle <provided-bundle.json>
python -m rfr.cli --root <directory> list --batch <batch-id>
python -m rfr.cli --root <directory> show --batch <batch-id> --item <item-id>
python -m rfr.cli --root <directory> draft --batch <batch-id> --item <item-id> --field merchant_name --action correct --value "Corrected Shop" --actor "local reviewer" --reason "Checked source"
python -m rfr.cli --root <directory> apply --batch <batch-id> --draft <saved-draft.json>
python -m rfr.cli --root <directory> export --batch <batch-id> --out <existing-private-export-directory>
```

Save the complete draft JSON unchanged before applying it. An exact retry uses that same file;
generating another draft changes timestamp/event identity. The default actor is agent-provisional.
An explicitly claimed human actor requires a reference but remains `unverified_human` in label exports.
Operational review does not certify independent human Gold.

`--mode clean` includes only resolved items and lists every omission. If no clean item exists, the CLI
writes an omission report and exits3 with `clean_export_empty`. Correcting a value alone does not waive
hard issues. Use `draft --waive-issue <current-issue-id> --issue-reason <explicit-reason>` for a recorded
disposition. Review exports include all registered items, including unresolved/deleted entries,
scalar/line-cell audit data and retained source metadata. CSV formula-leading text is escaped; JSONL
keeps original values.

`python -m pytest tests/pipeline tests/export tests/cli -q` exercises actual provided-bundle review,
restart/rerun, native process CAS, stale conflicts, clean refusal, exports and real CLI entrypoints.
Literal synthetic recognized pages and blocked network/provider imports are implementation controls,
not image OCR or real receipt accuracy measurements.

## Browser review viewer

Build from the repository root with Node 24, then serve the artifact with Python 3.12:

```text
npm ci --ignore-scripts
npm run build
python -m rfr.serve --root <existing-private-batch-directory> --viewer dist/web --port <explicit-loopback-port>
```

The host reads `RFR_LOCAL_CAPABILITY` from its environment: supply a fresh 32–256 character printable
ASCII capability before launch, then enter it in the viewer. The launcher binds only `127.0.0.1`,
prints no capability and disables receipt-path access logs. The fixed public HTML/JS/CSS shell
contains no receipt data or capability. Every API/read/export route still requires the capability;
mutations also require the exact same-origin browser Origin. No CORS proxy is used.

Create a single-currency batch or reopen its complete batch identity. Import recognized-bundle JSON,
select any scalar, line cell or adjustment, inspect its supplied text/region and unchanged machine
proposal/score, and save an explicit correction/confirmation/printed-absence waiver/reopen with a
reason. Ctrl+Enter saves. Issue waivers require selecting the exact issues and giving a reason.
Agent-provisional is the default; a claimed human reference stays unverified and is not human Gold.
A clean export can include explicitly waived conflicts; it is not a receipt-accuracy certification.

Unsaved edits and pending saved-draft retries block batch/item switching and export. A stale save
is refused; reload state preserves the typed text before another explicit decision. On an uncertain
apply response, retry the unchanged saved draft rather than generating another event. Do not reload
the page before saving: unsaved text, capability and pending drafts are memory-only. The URL fragment
remembers only the batch identity. Saved decisions live in the server journal and replay on restart.

The recognized source preview uses supplied line text/geometry, with the selected field region.
It is clearly labelled **Image unavailable**; it does not supply an original image or measured OCR.
No image upload, job execution, live method, static unsaved demo mode or hosted backend is added.
The static snapshot accepts only bounded index/hashed JS/CSS files and refuses private-root overlap,
links, unexpected files/directories and oversized artifacts. Responses carry a restrictive CSP.

`npm run test:viewer` exercises the client and actual React review component; `npm run test:review`
focuses on pending-intent recovery. Install both frozen Python and Node dependencies first. The React
checks use jsdom and a test-only stdio bridge to actual canonical file/journal services. Their explicit
fault withholds one success acknowledgement after a real commit; it is not native-browser input,
live HTTP packet loss or OS file-save proof. Keyboard and visible retry must reuse the same saved
draft, with no replacement intent or journal append. Genuine stale edits still refuse; unsaved
cancel does not dispatch. A pending draft cannot be discarded through the visible cancel control.
`npm run build` runs the real TypeScript compiler and Vite. `python -m pytest tests/api -q` checks actual ASGI hosting
and API separation. See development status for the separately retained browser journey evidence.

## Local recognized-bundle HTTP adapter

`rfr.api.app.create_app(existing_private_root, origin="http://127.0.0.1:<port>",
capability=<fresh ASCII token of 32–256 characters>)` returns the FastAPI ASGI app. The trusted host
supplies the private root, exact loopback origin and capability. The factory starts no listener,
issues no token and exposes no OpenAPI page. Do not embed the capability in a URL or public assets.

Every HTTP request requires the exact `Host` and `X-RFR-Token`. Mutations also require the exact
`Origin` and `Content-Type: application/json`. Duplicate security headers, cross-site fetches,
transfer encoding and invalid lengths are refused before body reads. Actual JSON bytes are bounded
independently of Content-Length (default 8 MiB + 4096 bytes), with at most 1024 ASGI messages and a
five-second receive deadline. The adapter returns closed error codes without request/body echoes.
Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

| Method / path | Input or result |
|---|---|
| GET `/api/status` | Current capabilities; images, HTTP jobs and live methods unavailable |
| POST `/api/batches` | `CreateBatch` → batch identity |
| POST `/api/batches/{batch}/recognized` | `RecognizedImport` → item identity and revision |
| GET `/api/batches/{batch}/items` | Bounded item summaries |
| GET `/api/batches/{batch}/items/{item}` | Typed review detail; no retained artifact bytes |
| POST `/api/batches/{batch}/items/{item}/draft` | `DraftRequest` → stable `DecisionDraft` |
| POST `/api/batches/{batch}/items/{item}/decisions` | Exact saved draft → append/retry outcome |
| GET `/api/batches/{batch}/exports/{review\|clean}/{filename}` | Four fixed export filenames |

Input models are in `src/rfr/api/models.py`; generated JSON/TypeScript contracts retain the same
wire forms. Export filenames are `receipts.csv`, `line_items.csv`, `receipts.jsonl`, `omitted.json`.
An empty clean data download returns 409 with omissions; the omission report remains downloadable.
Source-bearing JSONL is private review data. No client-provided output path is accepted.

`python -m pytest tests/api -q` exercises actual FastAPI/Starlette dispatch through TestClient and
direct ASGI streaming, durable correction replay through a new app, exact retries, stale conflicts,
clean refusal and explicit provisional waivers. These authored controls do not prove a TCP listener,
browser, source overlay, native OCR, held-out quality or a hosted service. Windows async control
socket pairs are permitted by the test harness; application socket connections remain denied.
The pinned Starlette version currently warns that its httpx TestClient backend is deprecated;
the warning is retained. `uv build --wheel` followed by `python tools/check_wheel.py dist` checks
the actual package includes runtime schemas and vendored license notices.

## Check the scaffold without keys or dependencies

From this repository root, use Python 3.12 and Node 24:

```text
python -m unittest discover -s tests/contracts -p "test_scaffold.py" -v
node --test tests/contracts/test_frontend_config.mjs
```

The checks exercise forbidden module dependencies and publication controls with positive and negative cases. They do not start a server, open sockets, install OCR, or call a provider. Native OCR, image-to-receipt integration, real held-out evaluation and frontend build are pending.

The setup also locks Pydantic, pytest/ruff, React/Vite/TypeScript. After the dependencies are installed with `uv sync --frozen` and `npm ci --ignore-scripts`, run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `npm run typecheck`. Type checking currently covers configuration and generated API contracts, not a React viewer.

With the installed Python environment, run `python -m pytest tests/module -q` for synthetic model and moved-copy checks, and `python tools/generate_schemas.py --check` for exact generated-schema parity. Generate schemas with the same helper without `--check` after a versioned model change. These checks use no provider keys, images or human-labelled corpus.

`python -m pytest tests/docio -q` checks the bounded TSV parser, hierarchy/confidence/coordinate assembly and its moved runtime. Literal native-format controls do not establish a native OCR installation or receipt-image accuracy.

`python -m pytest tests/fieldextract -q` checks generic candidate selection, binary verifier bindings, score/routing gates, domain-check application and the actual moved Fieldextract/Docio pair. Ports are synthetic controls, including a fake native-PDF source; real transport, source authority, calibration and receipt-specific extraction remain pending.

`python -m pytest tests/receipt -q` checks source-bound B0 candidates, all scalar/line-cell metadata, printed adjustments, exact Decimal arithmetic, ambiguous/future dates, printed currency and review-only defaults. Its literal recognized-page controls are implementation evidence; they do not measure accuracy on real receipt images. Currency parsing uses seven explicitly supported presets, with factual minor units checked against the [SIX currency list](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml) published 2026-09-17.

`python -m pytest tests/ports -q` checks a strict provided-frame OCR replay adapter. Registration binds immutable page input, expected engine/version/config and retained artifact bytes. Misses, recorded failures and caps return explicit failures with no native/live fallback. Synthetic versus recorded-replay labels stay visible; they do not authenticate a capture or measure OCR quality. No general replay-file loader or provider transport is implemented by this adapter.

`python -m pytest tests/rulings -q` exercises the bounded local journal, historical retries, CAS, damaged-tail refusal, scalar projection and moved-runtime closure. Windows process races, lock deadlines and process exit after fsync are tested with owned temporary files. POSIX and power-loss recovery remain unverified.

`python -m pytest tests/evalkit -q` exercises actual corpus hash/order checks, injected fixed-ID comparisons, hand-counted classification/set/agreement statistics, Wilson intervals, paired 2,000 whole-group bootstrap draws, separate failure populations and closed public aggregates. Tests use tiny authored synthetic controls, including a detached runtime with original app/provider imports and network disabled. They do not supply real receipts, independent human gold or performance results.

## Planned workflow

The intended image workflow imports up to100 single-currency JPEG/PNG/HEIC receipts, shows highlighted source regions, supports keyboard review, and exports CSV/JSONL. Provided recognized bundles already support durable corrections, unchanged-evidence reruns, changed-evidence conflicts and audited exports through the CLI. Durable recognized-item jobs execute B0 and retain explicit J1/V2-unavailable outcomes. Original image decoding/serving, image-upload jobs and the browser journey remain pending. API DTOs, generated TypeScript contracts and a pure request-policy guard exist; HTTP transport and actual stream enforcement remain pending.

## Architecture

The Python `rfr` core contains reusable [docio](src/rfr/shared/docio/README.md), [fieldextract](src/rfr/shared/fieldextract/README.md), [rulings](src/rfr/shared/rulings/README.md) and [evalkit](src/rfr/shared/evalkit/README.md) foundations. Each owns generated JSON schemas and declares its copy closure. Rulings includes a bounded owner-private journal and recorded-decision projection; its actor metadata does not authenticate a human. Evalkit executes generic statistics and injected comparisons; source rights, label provenance, independent held-out seals and authorized durable history remain caller responsibilities. Runtime decoders, receipt-domain scorers, live providers, API and the review viewer remain pending. The [file workflow](src/rfr/pipeline/README.md) and [canonical offline execution components](docs/vendor/execution/README.md) are implemented; mock/replay controls establish component behavior, not paid model quality.

Frozen lockfiles describe the installed scaffold dependencies. FastAPI/native OCR/provider SDKs and the actual review UI are deferred to their assigned work packages. There is no frontend `build` script yet, so scaffold green cannot be mistaken for an application build.

## Results and cost

Receipt accuracy, abstention, auto-accept precision, OCR quality, latency and model cost are **not yet measured**. No provider calls have been made. Synthetic implementation controls will be reported separately from real held-out results.

## Limits and portability

This is a recognized-bundle review foundation with a runnable synthetic demo. See [limitations](docs/LIMITATIONS.md), [architecture](docs/architecture.md), and the [schema boundaries](docs/schema-design.md). Python/native OCR requires a local or separately hosted runtime; an eventual static JavaScript viewer does not supply that backend. Image workflow, UI build, live integration, hosted deployment and public release remain pending.

Coding agents wrote the scaffold. Its dependency-free checks are reproducible above; those checks do not establish product acceptance.
