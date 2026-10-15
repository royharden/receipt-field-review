# Receipt Field Review

Development is paused as of 2026-10-15. See [current development status](DEVELOPMENT-STATUS.md)
for completed slices, unfinished work, validation limits and the next tasks, and [lessons](LESSONS.md)
for implementation findings. No runnable image application or frontend build is available yet.

Receipt Field Review proposes fixed receipt scalar/line-cell fields from supplied recognized pages, preserves review decisions across unchanged-evidence reruns, and exports private CSV/JSONL with field audit metadata. It uses four reusable foundations, a durable decision journal and canonical offline execution components. Image ingestion, actual native/model inference, the API and browser viewer remain under construction.

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

This is a recognized-bundle review foundation, not a finished image application. See [limitations](docs/LIMITATIONS.md), [architecture](docs/architecture.md), and the [schema boundaries](docs/schema-design.md). Python/native OCR requires a local or separately hosted runtime; an eventual static JavaScript viewer does not supply that backend. A product demo, UI build, live integration, hosted deployment and public release remain pending.

Coding agents wrote the scaffold. Its dependency-free checks are reproducible above; those checks do not establish product acceptance.
