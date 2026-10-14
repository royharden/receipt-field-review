# Architecture boundary

Current implementation: the `rfr` package initializer, root build-tool configuration and scaffold checks. Shared schema implementation, receipt extraction, storage, API and UI remain pending.

The intended dependency direction is:

```text
UI -> local API -> receipt workflow -> shared module protocols
fieldextract -> docio
rulings and evalkit -> generic schemas/standard libraries
app adapters -> canonical external owner modules
```

Shared modules must not depend on app namespaces. Each export owns its models and protocol definitions; the app injects adapters. Provider/ledger and screening implementations come from their actual owning projects at verified commits with provenance and contract checks. There are no such vendored modules yet.

The bounded local workflow uses files plus append-only JSONL and a rebuildable in-memory projection, not a second authoritative application database. An adopted ledger may independently use SQLite. Private images/records/caches live in an ignored `data/` root and must not enter static viewer assets.

The static viewer will be transient synthetic-only. It cannot supply Python, OCR, human-labelled data or a live provider. Public serving requires a separately approved authentication/storage/job/budget design.
