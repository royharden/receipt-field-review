# Receipt Field Review

Receipt Field Review is being built to extract receipt fields with source evidence, leave uncertain values for review, and preserve human corrections across reruns. The current repository contains the package scaffold and four reusable modules with wire models, injected ports and pure identity/evidence validators. It does not yet extract or review receipts.

## Check the scaffold without keys or dependencies

From this repository root, use Python 3.12 and Node 24:

```text
python -m unittest discover -s tests/contracts -p "test_scaffold.py" -v
node --test tests/contracts/test_frontend_config.mjs
```

The checks exercise forbidden module dependencies and publication controls with positive and negative cases. They do not start a server, open sockets, install OCR, or call a provider. These are scaffold checks; native OCR, extraction, evaluation and frontend build are pending.

The setup also locks Pydantic, pytest/ruff, React/Vite/TypeScript. After the dependencies are installed with `uv sync --frozen` and `npm ci --ignore-scripts`, run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `npm run typecheck`. Type checking currently covers configuration only.

With the installed Python environment, run `python -m pytest tests/module -q` for synthetic model and moved-copy checks, and `python tools/generate_schemas.py --check` for exact generated-schema parity. Generate schemas with the same helper without `--check` after a versioned model change. These checks use no provider keys, images or human-labelled corpus.

`python -m pytest tests/rulings -q` exercises the bounded local journal, historical retries, CAS, damaged-tail refusal, scalar projection and moved-runtime closure. Windows process races, lock deadlines and process exit after fsync are tested with owned temporary files. POSIX and power-loss recovery remain unverified.

## Planned workflow

Import a single-currency batch of up to 100 JPEG/PNG/HEIC receipts. Inspect fields alongside highlighted source regions, correct or confirm values with the keyboard, save and move to the next item, then export CSV/JSONL. Extraction reruns preserve decisions; changed evidence requires conflict resolution. This workflow is not implemented yet.

## Architecture

The Python `rfr` core contains reusable [docio](src/rfr/shared/docio/README.md), [fieldextract](src/rfr/shared/fieldextract/README.md), [rulings](src/rfr/shared/rulings/README.md) and [evalkit](src/rfr/shared/evalkit/README.md) foundations. Each owns generated JSON schemas and declares its copy closure. Rulings now includes a bounded owner-private journal and recorded-decision projection; its actor metadata does not authenticate a human. Receipt rules, app storage/API and UI will adapt these modules. Runtime decoders, scoring/statistics engines, providers, domain adapters and the review viewer remain pending.

Frozen lockfiles describe the installed scaffold dependencies. FastAPI/native OCR/provider SDKs and the actual review UI are deferred to their assigned work packages. There is no frontend `build` script yet, so scaffold green cannot be mistaken for an application build.

## Results and cost

Receipt accuracy, abstention, auto-accept precision, OCR quality, latency and model cost are **not yet measured**. No provider calls have been made by this scaffold. Replay/conformance results will be reported separately from real held-out results when the evaluator exists.

## Limits and portability

This is a foundation slice, not a finished application. See [limitations](docs/LIMITATIONS.md), [architecture](docs/architecture.md), and the [schema boundaries](docs/schema-design.md). Python/native OCR requires a local or separately hosted runtime; an eventual static JavaScript viewer does not supply that backend. A product demo, UI build, live integration, hosted deployment and public release remain pending.

Coding agents wrote the scaffold. Its dependency-free checks are reproducible above; those checks do not establish product acceptance.
