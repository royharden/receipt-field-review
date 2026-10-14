# Current limitations

The repository contains a scaffold plus four reusable models/ports/pure-validation foundations and generated schemas. Receipt ingestion, native HEIC conversion, actual OCR, candidate extraction, model verification, durable review, scoring/statistical engines, API/UI and exports are not implemented.

The Python/Node checks verify architecture and publication controls. Synthetic module tests verify schema/identity/evidence admission and moved model closures. They do not prove OCR quality, receipt-field accuracy, durable append/CAS/reducers, statistical computations, provider stability, a frontend build, browser persistence, hosted isolation or app acceptance.

Required later evidence includes native HEIC, a lawful real 30-item OCR comparison, browser overlay/correction/restart/stale-tab behavior, module consumer contracts and three-method measured results. Real datasets, applicable terms, human-corrected gold, and a full paid evaluation grant remain prerequisites. Synthetic/replay data cannot satisfy those real-data claims.

The declared default for 100 phone receipts is 60 dev / 40 held-out with review-only fields when the strict lower-95%-Wilson precision gate cannot be met. No measured automation or accuracy result exists yet.

Python/native OCR is an external runtime boundary for the eventual static viewer. No hosted database, GitHub remote, Bolt import, backend provisioning or public release is established by this scaffold.
