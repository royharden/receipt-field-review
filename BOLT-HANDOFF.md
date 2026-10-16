# Bolt handoff: Receipt Field Review

## Target and readiness

- App root: this product repository; branch `main`.
- Status: recognized-bundle CLI, HTTP adapter, browser viewer and synthetic local demo implemented; image application incomplete.
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
controls through real loopback HTTP. Native HEIC/OCR, original-image and live receipt methods remain
separate. Browser evidence is scoped to the exact built artifact, host and authored input.

The HTTP factory's exact loopback Host/token/Origin policy, actual streamed-byte/message limits,
body deadline, closed errors and private download headers are exercised in process. FastAPI,
Uvicorn and httpx are installed from the portable public-registry lock; the viewer continuation launches a bounded real loopback server for authored browser checks.
The host must supply a fresh capability and existing private root. See the README for the route
inventory and body bounds. HTTP job control, image endpoints and source-image bytes remain absent.

Complete image decoding/preprocessing/OCR, actual listener/worker ownership, original-image source overlays, canonical live method integration and required independent evaluation before presenting
the full app as ready. Rights, genuine human labels, frozen held-out data and applicable spend grants
remain separate prerequisites. [Development status](DEVELOPMENT-STATUS.md) tracks those product gaps.

## Inspection prompt after an authorized import

> Read BOLT-HANDOFF.md and inspect this product repository at the intended revision. Identify the
> runnable recognized-bundle demo and the implemented recognized-bundle viewer and incomplete image/job/native boundaries. Prepare a concrete
> deployment-gap inventory while preserving the local files/JSONL architecture and existing code.
> Do not infer a hosted Python/OCR runtime from a static viewer or add an unnecessary database.
> Do not create/change cloud resources, apply migrations, deploy functions, enter secrets, enable
> schedules or publish. Report required backend hosting and remaining owner steps with actual checks.
