# rulings: intent, event and receipt wires

Implemented: strict scalar/pair subjects and payloads; opaque two-field record identity; canonical
pair key and separately aligned raw-generation preimages; complete client-intent serialization;
store-sequence exclusion and historical exact-retry receipt shape. Scalar null/false values retain
their types. Reopen/retraction payloads do not implicitly assert current approval.

Copy closure: this directory's Python files, schema.json and README with root MIT LICENSE;
Python3.12/Pydantic2. It imports no docio, matching, receipt, provider or UI code. Raw-record fingerprints
and current-source validation use the consumer-injected producer profile (including product-raw-fields-v1
where applicable); there is no invented generic row hash or matching reducer here.

No journal, append/fsync, lock/CAS, idempotent storage, crash recovery, projection, tombstone handling,
human authentication or effective-decision reducer is implemented. Wire validation checks internal
identity consistency and branch shape, not current heads or historical target existence. Actor labels
are attribution, not permissions. Store/reducer/validator protocols state later integration seams;
model-only tests are not durability or reduction evidence.
