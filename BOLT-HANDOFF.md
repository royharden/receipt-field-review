# Bolt handoff: Receipt Field Review

## Target and readiness

- App root: this product repository; branch `main`.
- Status: recognized-bundle CLI/HTTP/viewer and synthetic demo implemented; optional installed-engine image-to-B0/review CLI joined; image HTTP/worker/UI application incomplete.
- Database: **No database required** for the local MVP. Private files, an append-only JSONL rulings
  journal and a rebuildable projection hold app state. Vendored provider-ledger code may independently
  use SQLite; it is not connected to live receipt inference.
- Hosting: local Python runtime. Python/native OCR, private filesystem storage and an HTTP worker
  remain separate hosting/integration work. The frontend has a real Vite build served by the same-origin loopback Python host.
- Bolt action: inspect and prepare only. GitHub import, hosting, cloud resources and publication
  have not been exercised. No database, auth connection or deployed baseline is asserted.

## Implemented inventory and commands

| Item | Source / command |
|---|---|
| Runtime | Python 3.12; uv frozen lockfile; Node 24 for existing frontend checks |
| Setup | `uv sync --frozen`; existing npm scaffold uses `npm ci --ignore-scripts` |
| Keyless demo | Create an owner-controlled `data/` parent, then `uv run --no-sync python scripts/demo.py --mode mock --out data/recognized-demo` |
| Bundle CLI | `python -m rfr.cli --help`; validates recognized bundles, saves decisions and exports private CSV/JSONL |
| Optional image staging | `uv sync --frozen --extra heic`; `python -m rfr.ingest --source <image> --out <existing-private-parent>` retains original/normalized PNG/manifest; no OCR or receipt import |
| Local native import | `python -m rfr.cli --root <private-root> import-image --batch <id> --source <image> --tesseract <installed-executable> --tessdata <model-directory> --reference-date <ISO-date>`; existing review CLI then corrects/exports the imported item |
| Core | `src/rfr/shared/{docio,fieldextract,rulings,evalkit}`; receipt plugin and `src/rfr/pipeline` |
| HTTP/frontend | `rfr.api.app.create_app`: recognized-bundle FastAPI factory, bounded actual ASGI requests and durable review/export; recognized-bundle React viewer and optional bounded public shell |
| HTTP checks | `python -m pytest tests/api -q`; actual in-process requests, no source images or live methods |
| Package check | `uv build --wheel`; `python tools/check_wheel.py dist` verifies shipped schemas/licenses |
| Focused tests | `python -m pytest tests/demo tests/pipeline tests/export tests/cli -q` |
| Combined checks | `python -m pytest -q`; `python -m ruff check .`; `python -m ruff format --check .` |
| Generated contracts | `python tools/generate_schemas.py --check`; `python tools/generate_api_contract.py --check` |
| Frontend checks | `npm run typecheck`; `node --test tests/contracts/test_frontend_config.mjs` |
| Frontend build/output | `npm run build` → `dist/web`; `npm run test:viewer` checks client boundaries |
| Local viewer | Set trusted `RFR_LOCAL_CAPABILITY`; `python -m rfr.serve --root <private-root> --viewer dist/web --port <explicit-port>` |

The demo processes only a pinned agent-authored recognized bundle, persists provisional corrections,
refuses unresolved clean exports, records explicit synthetic issue waivers and performs a real local
B0 rerun. `DEMO.json` is written last with input/output digests. It supplies no source image,
measured OCR geometry/confidence, model transport, human Gold or accuracy result.

## Pending-decision repair and test boundary

The review controller guards pending drafts at every entry point. Ctrl+Enter and the visible retry
reuse the retained draft/event identity; normal save cannot generate a replacement while recovery
is pending. `npm run test:review` runs actual React rendering with synthetic DOM events and a real
canonical file/journal test port, including an explicit acknowledgement fault after a real commit.
It preserves genuine stale refusal and cancel behavior. This is not a native browser/lost-response
or OS file-save gate. Independent review qualified the bounded pending-intent construction repair;
the earlier viewer candidate remains unaccepted, and required native UI, real HTTP committed-response
loss and native save evidence remain open. No cloud readiness follows from the construction result.

## Image staging boundary

Optional Pillow 12.3.0 and pillow-heif 1.8.1 are pinned in the portable uv lock. A separate local
command now stages bounded PNG/JPEG/HEIC into a private content-addressed directory, retaining
original bytes and a metadata-stripped normalized PNG. It records hashes, dimensions and explicit
orientation/grid provenance; malformed, oversized, multi-image and changed/partial output refuse.
Real Windows codec controls use authored pixels. A separate explicit `import-image` CLI now runs
an installed English Tesseract engine and joins actual retained TSV through canonical Docio/B0,
ReceiptBundle and existing review storage. The default recognized-only installation is unchanged.
The native run records binary/model/configuration/source/grid hashes, process limits and failures.
Authored native functional controls exercise correction, exact retry, repeated OCR, reopen and
exports. A first version probe timed out; stable startup and the broad Python gate remain
unresolved. Native functional evidence does not establish receipt accuracy or engine selection.
Image HTTP jobs, worker control and viewer overlays remain pending.
The later joined check retained two failures (native startup and a 20-second review child wait).
A moved-runtime comparison passed four cases but native import still exhausted its total
30-second operation budget after successful engine commands. Native timing and the combined gate
remain open; packaging checks do not qualify this boundary for deployment.
The new optional Linux CI job is configured but has not run remotely. Python/native dependencies
still require a local or separately hosted backend; Bolt import/provisioning is unperformed.

The installed engine and model are read-only external requirements, not bundled repository assets.
Preserve [third-party provenance](docs/THIRD-PARTY.md): the optional HEIC wrapper metadata says
BSD-3-Clause, while the inspected Windows binary wheel's bundled notice says GPLv2 due to base
libraries. The installed Tesseract notice and actual model/library fingerprints are retained
separately; model source/licence provenance and distribution qualification remain unverified.
No compatibility or clean-distribution verdict is supplied by local execution.

## Infrastructure inventory

Migrations, hosted tables/RLS, buckets, edge functions, external auth providers, callback URLs,
Realtime, schedules and webhooks: **not required by this local demo; none provisioned**.
Demo secrets/public environment variables: **none required**. There is no live fallback.
Keep provider keys in a future trusted backend only, after its exact runtime/spend authorization.

Output belongs in an existing owner-controlled local parent. Demo output uses exclusive new
directories; the workflow journal retains audit history and rejects stale decisions. These local
controls do not establish hostile multiuser filesystem or deployed tenant isolation. A public server
requires a separate authentication, upload storage, worker lifetime and budget design.

## Verification boundaries and remaining work

Local demo tests exercise fresh subprocess correction replay, actual B0 rerun, provisional labels,
machine-evidence preservation, explicit conflict waivers, malformed-bundle refusal and no-overwrite
behavior with provider/native imports and sockets blocked. See the reproducible commands above.
The later viewer has actual root TypeScript/Vite build and synthetic Chromium correction/stale/refusal
controls through real loopback HTTP. The separate native CLI image-to-OCR/B0 join does not supply
original-image browser overlays or live receipt methods. Browser evidence remains scoped to its
exact built artifact, host and authored input.

The HTTP factory's exact loopback Host/token/Origin policy, actual streamed-byte/message limits,
body deadline, closed errors and private download headers are exercised in process. FastAPI,
Uvicorn and httpx are installed from the portable public-registry lock; the viewer continuation launches a bounded real loopback server for authored browser checks.
The host must supply a fresh capability and existing private root. See the README for the route
inventory and body bounds. HTTP job control, image endpoints and source-image bytes remain absent.

Complete the remaining preprocessing/engine qualification, actual listener/worker ownership, original-image source overlays, canonical live method integration and required independent evaluation before presenting
the full app as ready. Rights, genuine human labels, frozen held-out data and applicable spend grants
remain separate prerequisites. [Development status](DEVELOPMENT-STATUS.md) tracks those product gaps.

## Inspection prompt after an authorized import

> Read BOLT-HANDOFF.md and inspect this product repository at the intended revision. Identify the
> runnable recognized-bundle demo, explicit local Tesseract import, recognized-bundle viewer and incomplete image/job/hosting boundaries. Prepare a concrete
> deployment-gap inventory while preserving the local files/JSONL architecture and existing code.
> Do not infer a hosted Python/OCR runtime from a static viewer or add an unnecessary database.
> Do not create/change cloud resources, apply migrations, deploy functions, enter secrets, enable
> schedules or publish. Report required backend hosting and remaining owner steps with actual checks.
