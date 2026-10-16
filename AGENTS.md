# Receipt Field Review agent instructions — version 8

Product code, tests and stable product documentation belong in this Git repository. Plans, agent identity registries, private reviews, transcripts, execution receipts and live resource records belong in the designated outer workspace, never here. A moved product repository must not depend on absolute workspace imports.

## Commands and current state

The repository has four reusable foundations, a bounded rulings journal/projection, an injected evaluation/statistics engine and generic candidate selection/check/routing. Python 3.12 and Node 24 are the declared runtimes. An optional installed-Tesseract CLI now joins staged images to canonical Docio/B0 and the existing review workflow. Real held-out results, live methods and the image HTTP/worker/UI join remain pending.

```text
python -m unittest discover -s tests/contracts -p "test_scaffold.py" -v
node --test tests/contracts/test_frontend_config.mjs
```

Those dependency-free checks install nothing. The assigned setup adds frozen Pydantic/pytest/ruff and React/Vite/TypeScript dependencies; `uv sync --frozen`, `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `npm ci --ignore-scripts`, and `npm run typecheck` verify that setup. See package.json and README for current frontend check/build coverage. Never claim a scaffold check is extraction accuracy, a frontend build, deployed security or a finished app.

Model checks use the installed environment: `python -m pytest tests/module -q` and `python tools/generate_schemas.py --check`. Generated schemas are module-owned. Models are closed/strict; geometry and provenance cannot be upgraded by shape validation. Consumer modules may be moved only with the closure declared in each module README and root LICENSE. New runtime behavior requires its own implementation and failure-capable checks.

Journal checks use `python -m pytest tests/rulings -q`. They cover bounded owner-private paths, full-intent historical retry before stale CAS, native Windows process locks/deadlines, fsync before success, damaged-tail preservation/read-only refusal, recorded scalar/pair barriers and detached runtime. POSIX/power-loss behavior is not verified. Never convert actor/ref syntax or provisional annotations into actual human/gold evidence. Repair is a separate explicit policy; never truncate a damaged journal automatically.

Evaluation checks use `python -m pytest tests/evalkit -q`: tiny authored synthetic controls for fixed corpus/order/hash, source failures, private/public inputs, hand-counted rates, Wilson uncertainty, paired 2,000 whole-group draws, explicit not-run reports and actual detached runtime. Human provenance, lawful source rights, independent seals and durable authorized exposure history remain caller gates. These controls do not establish actual held-out performance or calibration.

Extraction checks use `python -m pytest tests/fieldextract -q`: bounded candidate/question/answer admission, source preflight, diagnostic score tables, default review/calibration/hard gates, a fake native-PDF source and actual moved sibling closure. Injected ports do not supply budget authority, source authenticity, actual model transport or calibration proof. Never replace independent verifier questions with one exclusive hazard distribution.

Receipt checks use `python -m pytest tests/receipt -q`: fixed complete scalar/line-cell schema, source-bound overfinding/B0, Decimal minor-unit checks, explicit adjustment stages, conservative dates/currency and review-only defaults. Missing quantity/operands remain unknown; never guess one/zero. Locale/currency/reference date must be explicit. Raw recognized artifacts and candidate banks remain separate retained inputs; no real image accuracy or automation result is established by literal controls.

Native controls use `python -m pytest tests/ports/test_tesseract_process.py tests/ingest/test_native.py -q` with optional image dependencies. The actual installed-engine case additionally requires explicit `RFR_TEST_TESSERACT`, `RFR_TEST_TESSDATA` and `RFR_TEST_FONT` paths; without them it is skipped, not passed. The app-local adapter consumes the existing Docio protocol/TSV parser, B0 and BatchStore without changing canonical wire ownership. Preserve original/normalized/grid/TSV/engine/config identities, bounded child outputs/deadlines and failed/incomplete attempts. Native functional controls use authored pixels, not real-receipt accuracy or a qualified engine comparison. Keep prior startup/full-run failures visible; native CLI success does not close image HTTP/UI/save or whole-app gates. Third-party provenance, including the HEIC wrapper/binary licence distinction, is in docs/THIRD-PARTY.md.

## Invariants

- Generic shared modules own their schemas and injected protocols. They must not import receipt/pipeline/methods/ports/API/export/CLI/UI code. The only proposed owned-module dependency is fieldextract -> docio; unadopted wire schemas remain proposals.
- Source regions use one declared source-page pixel frame, explicit dimensions/hash/page convention and preprocessing transform. Model-claimed boxes are not measured evidence. Missing confidence remains unknown.
- Corrections use append-only durable events, source/prior-revision compare-and-set and explicit conflicts. Re-extraction never silently overwrites a human decision.
- Absent, abstained and unlabelled differ. Arithmetic/date/currency checks run in code. Missing operands are not a successful check. Uncalibrated or insufficient-data strata remain review-only.
- Ordinary fixtures are synthetic, owned or explicitly cleared public data. Gold manifests will live in `gold/`, with grouped dev/held-out splits frozen before tuning. No real uploads or uncleared images/labels/derived responses may be committed.
- API keys belong only in trusted server processes. No public frontend variable, command argument, log, fixture, image layer or committed file may contain a key. Mock/cached mode cannot silently fall back to a paid request.
- A live call needs the adopted canonical provider/ledger controller, trusted spend authority and complete bounded reservation, including retry/fan-out/unknown liabilities. Estimated tokens alone do not prove a spend bound.
- Before any listener or Docker resources, use the project's resource registration policy. Start and clean up only assigned, owned resources. Do not choose a port to bypass that policy.
- Independent app acceptance is separate from an author's or its child's advisory checks.

## Applicable canonical skills

Use the current workspace's pinned delivery and plan-adoption rules when participating in that run. Global canonical skills are available from `C:/Users/Roy Harden/OneDrive/PJ-OD/skills` (not vendored into this public product):

- `ai-first-persistent-memory-and-planning-framework/SKILL.md`: recon, scoped changes and lean stable documentation; workspace outer-shell storage overrides generic scratch placement.
- `sync-skills-across-agents/SKILL.md`: changes to these instruction files or skill references.
- `skills-bts/bolt-new-infrastructure/SKILL.md`: actual portability/handoff inventory, without inventing backend provisioning.
- `skills-bts/typesafe-ai/SKILL.md`: current official docs before any Jev integration.
- `skills-bts/agent-ports/SKILL.md`: resources before listening or Docker.

Skill paths describe the development environment, not runtime imports. Do not copy skills, credentials or coordination history into the product. Claude imports this file; Cursor has a pointer; Grok/Codex read this root instruction file. No separate local skill mirrors are introduced.

Changelog: v1 established bootstrap commands/invariants. v2 locked scaffold dependencies. v3 added models/schema parity/moved closures. v4 added journal commands and durability/provenance limits. v5 added evaluation/statistics controls. v6 added generic extraction. v7 added receipt-plugin commands. v8 records the explicit app-local native CLI/controls and remaining real-data/HTTP/UI/acceptance boundaries. Claude/Cursor pointers continue to import this single instruction source; no hook or skill mirror is changed.
