# Proposed schema boundaries — not adopted wire schemas

This is design scaffolding. No shared schema or domain resolver is implemented here. Counterpart adoption and versioned contract vectors precede exported-schema code.

| Boundary | Proposed ownership | Required semantics |
|---|---|---|
| Document / Page / Block / Word / Line | docio | stable identities; source-kind independent of receipt images; source-page dimensions/hash; explicit pixel coordinates and transform; nullable OCR confidence and per-element geometry provenance |
| Document region pointer | docio coordinates + external tagged Pointer owner | page hash/index and coordinate units; zero-based page convention; source generation binding; stale/unsupported evidence errors; normalized views are derived |
| FieldValue / Candidate / FieldSpec | fieldextract | nullable visible value, preserved machine proposal, score components/source/method/status/issues; closed candidate selection; generic injected selection/verifier/check protocols |
| Ruling envelope / scalar payload | rulings | namespace and stable subject; tagged event version; source/prior CAS; old/new/who/time; append durability and idempotency; source conflicts and fail-closed damaged tails |
| Pair/tombstone payload | matching owner with rulings envelope adoption | structured namespaced refs/fingerprints; collision-safe serialization; explicit invalidation; no scalar reinterpretation |
| Gold record / manifest / outcomes | evalkit | present/absent/unlabelled; grouped split/seed/freeze/source provenance; failures kept; zero-denominator NA; human outcomes separate from machine precision |
| Provider / ledger requests | external provider/ledger owner | discriminated text/typed/image capability; requested/resolved model; provider-reported nullable usage; complete pre-call fan-out/retry reservation; unknown liabilities retained |

Receipt composite schemas belong to the app plugin. Copying a generic module must not require the receipt application. A later PDF/native page source must run the same generic consumer without an invented OCR probability. Readme/schema names are not proof that a canonical external interface has been adopted.
