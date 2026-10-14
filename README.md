# Receipt Field Review

Receipt Field Review is being built to extract receipt fields with source evidence, leave uncertain values for review, and preserve human corrections across reruns. The current repository contains the package/configuration scaffold and dependency-free architecture/publication checks; it does not yet extract or review receipts.

## Check the scaffold without keys or dependencies

From this repository root, use Python 3.12 and Node 24:

```text
python -m unittest discover -s tests/contracts -p "test_scaffold.py" -v
node --test tests/contracts/test_frontend_config.mjs
```

The checks exercise forbidden module dependencies and publication controls with positive and negative cases. They do not start a server, open sockets, install OCR, or call a provider. These are scaffold checks; native OCR, extraction, evaluation and frontend build are pending.

The setup also locks Pydantic, pytest/ruff, React/Vite/TypeScript. After the dependencies are installed with `uv sync --frozen` and `npm ci --ignore-scripts`, run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `npm run typecheck`. Type checking currently covers configuration only.

## Planned workflow

Import a single-currency batch of up to 100 JPEG/PNG/HEIC receipts. Inspect fields alongside highlighted source regions, correct or confirm values with the keyboard, save and move to the next item, then export CSV/JSONL. Extraction reruns preserve decisions; changed evidence requires conflict resolution. This workflow is not implemented yet.

## Architecture

The Python `rfr` core will own independently reusable `docio`, `fieldextract`, `rulings` and `evalkit` modules. Receipt rules, local storage, API and UI will adapt those modules. React/Vite will supply a loopback review viewer and a clearly labelled, transient synthetic static preview. Shared owner/consumer schemas are still proposals and are not implemented in the scaffold.

Frozen lockfiles describe the installed scaffold dependencies. FastAPI/native OCR/provider SDKs and the actual review UI are deferred to their assigned work packages. There is no frontend `build` script yet, so scaffold green cannot be mistaken for an application build.

## Results and cost

Receipt accuracy, abstention, auto-accept precision, OCR quality, latency and model cost are **not yet measured**. No provider calls have been made by this scaffold. Replay/conformance results will be reported separately from real held-out results when the evaluator exists.

## Limits and portability

This is a bootstrap, not a finished application. See [limitations](docs/LIMITATIONS.md), [architecture](docs/architecture.md), and the proposed [schema boundaries](docs/schema-design.md). Python/native OCR requires a local or separately hosted runtime; an eventual static JavaScript viewer does not supply that backend. A product demo, UI build, live integration, hosted deployment and public release remain pending.

Coding agents wrote the scaffold. Its dependency-free checks are reproducible above; those checks do not establish product acceptance.
