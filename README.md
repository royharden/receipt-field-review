# Receipt Field Review

Receipt Field Review is being built to extract receipt fields with source evidence, leave uncertain values for review, and preserve human corrections across reruns. It can propose the fixed receipt scalar/line-cell schema from supplied recognized pages, using four reusable foundations, a bounded decision journal and an injected evaluator. Image ingestion and the review workflow remain under construction.

## Check the scaffold without keys or dependencies

From this repository root, use Python 3.12 and Node 24:

```text
python -m unittest discover -s tests/contracts -p "test_scaffold.py" -v
node --test tests/contracts/test_frontend_config.mjs
```

The checks exercise forbidden module dependencies and publication controls with positive and negative cases. They do not start a server, open sockets, install OCR, or call a provider. Native OCR, receipt extraction, real held-out evaluation and frontend build are pending.

The setup also locks Pydantic, pytest/ruff, React/Vite/TypeScript. After the dependencies are installed with `uv sync --frozen` and `npm ci --ignore-scripts`, run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `npm run typecheck`. Type checking currently covers configuration only.

With the installed Python environment, run `python -m pytest tests/module -q` for synthetic model and moved-copy checks, and `python tools/generate_schemas.py --check` for exact generated-schema parity. Generate schemas with the same helper without `--check` after a versioned model change. These checks use no provider keys, images or human-labelled corpus.

`python -m pytest tests/docio -q` checks the bounded TSV parser, hierarchy/confidence/coordinate assembly and its moved runtime. Literal native-format controls do not establish a native OCR installation or receipt-image accuracy.

`python -m pytest tests/fieldextract -q` checks generic candidate selection, binary verifier bindings, score/routing gates, domain-check application and the actual moved Fieldextract/Docio pair. Ports are synthetic controls, including a fake native-PDF source; real transport, source authority, calibration and receipt-specific extraction remain pending.

`python -m pytest tests/receipt -q` checks source-bound B0 candidates, all scalar/line-cell metadata, printed adjustments, exact Decimal arithmetic, ambiguous/future dates, printed currency and review-only defaults. Its literal recognized-page controls are implementation evidence; they do not measure accuracy on real receipt images. Currency parsing uses seven explicitly supported presets, with factual minor units checked against the [SIX currency list](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml) published 2026-09-17.

`python -m pytest tests/ports -q` checks a strict provided-frame OCR replay adapter. Registration binds immutable page input, expected engine/version/config and retained artifact bytes. Misses, recorded failures and caps return explicit failures with no native/live fallback. Synthetic versus recorded-replay labels stay visible; they do not authenticate a capture or measure OCR quality. No general replay-file loader or provider transport is implemented by this adapter.

`python -m pytest tests/rulings -q` exercises the bounded local journal, historical retries, CAS, damaged-tail refusal, scalar projection and moved-runtime closure. Windows process races, lock deadlines and process exit after fsync are tested with owned temporary files. POSIX and power-loss recovery remain unverified.

`python -m pytest tests/evalkit -q` exercises actual corpus hash/order checks, injected fixed-ID comparisons, hand-counted classification/set/agreement statistics, Wilson intervals, paired 2,000 whole-group bootstrap draws, separate failure populations and closed public aggregates. Tests use tiny authored synthetic controls, including a detached runtime with original app/provider imports and network disabled. They do not supply real receipts, independent human gold or performance results.

## Planned workflow

Import a single-currency batch of up to 100 JPEG/PNG/HEIC receipts. Inspect fields alongside highlighted source regions, correct or confirm values with the keyboard, save and move to the next item, then export CSV/JSONL. Extraction reruns preserve decisions; changed evidence requires conflict resolution. This complete image-to-review workflow is not implemented yet.

## Architecture

The Python `rfr` core contains reusable [docio](src/rfr/shared/docio/README.md), [fieldextract](src/rfr/shared/fieldextract/README.md), [rulings](src/rfr/shared/rulings/README.md) and [evalkit](src/rfr/shared/evalkit/README.md) foundations. Each owns generated JSON schemas and declares its copy closure. Rulings includes a bounded owner-private journal and recorded-decision projection; its actor metadata does not authenticate a human. Evalkit executes generic statistics and injected comparisons; source rights, label provenance, independent held-out seals and authorized durable history remain caller responsibilities. Runtime decoders, receipt scorers, providers, app storage/API and the review viewer remain pending.

Frozen lockfiles describe the installed scaffold dependencies. FastAPI/native OCR/provider SDKs and the actual review UI are deferred to their assigned work packages. There is no frontend `build` script yet, so scaffold green cannot be mistaken for an application build.

## Results and cost

Receipt accuracy, abstention, auto-accept precision, OCR quality, latency and model cost are **not yet measured**. No provider calls have been made. Synthetic implementation controls will be reported separately from real held-out results.

## Limits and portability

This is a foundation slice, not a finished application. See [limitations](docs/LIMITATIONS.md), [architecture](docs/architecture.md), and the [schema boundaries](docs/schema-design.md). Python/native OCR requires a local or separately hosted runtime; an eventual static JavaScript viewer does not supply that backend. A product demo, UI build, live integration, hosted deployment and public release remain pending.

Coding agents wrote the scaffold. Its dependency-free checks are reproducible above; those checks do not establish product acceptance.
