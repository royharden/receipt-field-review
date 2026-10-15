# Schema boundaries — models and pure validators

The four reusable modules implement adopted wire foundations, generated schemas and pure identity/evidence validators. Rulings also implements a bounded journal, replay and scalar/pair decision barriers; matching graph reducers remain consumer-owned. Native Windows process controls are tested; POSIX and power-loss recovery remain unverified. Evalkit executes generic statistics and injected fixed-ID corpus/comparison/reporting controls. Domain resolvers, provider/ledger controllers, OCR and receipt-domain scorers remain pending. Module READMEs identify actual copy closures and limits; schema checks do not establish runtime capabilities.

Evalkit Outcome and MetricRow use the adopted JSON key `class`; Python exposes `class_name` internally. JSON rejects the unadopted `class_name` key. Human-effective predictions remain separate from raw machine scoring. Typed manifest admission hashes include declared defaults and do not substitute for an original retained-file digest, actual independent seal or durable authorized history.

| Boundary | Proposed ownership | Required semantics |
|---|---|---|
| Document / Page / Block / Word / Line | docio | stable identities; source-kind independent of receipt images; source-page dimensions/hash; explicit pixel coordinates and transform; nullable OCR confidence and per-element geometry provenance |
| Document region pointer | docio coordinates + external tagged Pointer owner | page hash/index and coordinate units; zero-based page convention; source generation binding; stale/unsupported evidence errors; normalized views are derived |
| FieldValue / Candidate / FieldSpec | fieldextract | nullable visible value, preserved machine proposal, score components/source/method/status/issues; closed candidate selection; generic injected selection/verifier/check protocols |
| Ruling envelope / scalar payload | rulings | namespace and stable subject; tagged event version; source/prior CAS; old/new/who/time; append durability and idempotency; source conflicts and fail-closed damaged tails |
| Pair/tombstone payload | matching owner with rulings envelope adoption | structured namespaced refs/fingerprints; collision-safe serialization; explicit invalidation; no scalar reinterpretation |
| Gold record / manifest / outcomes | evalkit | present/absent/unlabelled; grouped split/seed/freeze/source provenance; failures kept; zero-denominator NA; human outcomes separate from machine precision |
| Provider / ledger requests | external provider/ledger owner | discriminated text/typed/image capability; requested/resolved model; provider-reported nullable usage; complete pre-call fan-out/retry reservation; unknown liabilities retained |

Receipt composite schemas belong to the app plugin and remain pending. Copying a generic module must not require the receipt application. Synthetic native/text Page tests preserve nullable confidence; they do not prove an installed PDF or OCR engine. External tagged Pointer/provider/controller classes remain owner-supplied adapters and must be verified against actual source releases before integration.
