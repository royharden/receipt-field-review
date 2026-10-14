# Current limitations

The repository currently contains only a bootstrap scaffold. Receipt ingestion, native HEIC conversion, OCR boxes, candidate extraction, model verification, durable review, API/UI and exports are not implemented.

The Python and Node scaffold checks verify architectural boundaries and publication controls. They do not prove OCR quality, receipt-field accuracy, provider stability, a frontend build, real browser persistence, hosted isolation or app acceptance.

Required later evidence includes native HEIC, a lawful real 30-item OCR comparison, browser overlay/correction/restart/stale-tab behavior, module consumer contracts and three-method measured results. Real datasets, applicable terms, human-corrected gold, and a full paid evaluation grant remain prerequisites. Synthetic/replay data cannot satisfy those real-data claims.

The declared default for 100 phone receipts is 60 dev / 40 held-out with review-only fields when the strict lower-95%-Wilson precision gate cannot be met. No measured automation or accuracy result exists yet.

Python/native OCR is an external runtime boundary for the eventual static viewer. No hosted database, GitHub remote, Bolt import, backend provisioning or public release is established by this scaffold.
