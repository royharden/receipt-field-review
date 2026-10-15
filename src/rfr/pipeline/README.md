# Bounded private review workflow

`BatchStore.create(existing_private_data_root, CurrencyPolicy(...))` creates one generated batch
directory. `register(ReceiptBundle(...), expected_revision=...)` stores a bounded, validated one-page
Docio document, exact retained OCR artifact and untouched machine receipt. A batch contains at most100
indexed identities under one currency policy. A tombstoned identity cannot be restored; a fresh upload
must receive a new identity. Traversal, static links/reparse files, foreign artifacts, malformed files
and mixed currency fail closed. These checks assume an owner-controlled local directory and ancestors.

Source heads live in an atomically replaced manifest and immutable content-addressed `runs` files.
The existing append-only rulings journal is the sole decision authority. Every app source update,
decision and projection takes a batch file lock before the public journal API. Generation checks and
append therefore cannot race other app source mutations; no journal private methods are used. Failed
temporary files, orphaned immutable bundles and damaged journal bytes are preserved, with no automatic
repair. File fsync and native Windows locks are exercised; OS power-loss durability and a hostile
multiuser filesystem are not established.

The review projection keeps raw machine proposals, evidence, scores and confidence separate from
effective corrections. Confirm/correct/waive/reopen decisions require an exact prior head, current
item revision, current evidence generation and old typed value. Identical retries remain historical
even after a rerun or deletion. The artifact plus interpretation context defines evidence generation;
an identical-evidence method rerun preserves decisions, while changed OCR/context requires review.
Reopen does not revive an older correction. Actor labels never certify independent human Gold.

All seven scalar fields, every line cell and printed adjustment remain visible. Clean export requires
resolved fields and explicit dispositions for remaining issues; correcting a number alone does not
waive hard flags. Effective values are checked again. Check issue identifiers bind the current operand
values, so an old waiver does not silently cover changed values. A valid printed future date can be
reviewed while its failed check remains visible. Review export includes unresolved and deleted items;
clean export lists every omission and reason. CSV protects formula-leading text and retains per-field
audit metadata, with a separate line-items CSV. JSONL preserves exact machine/source metadata. Output
sets use exclusive generated directories and a final completion marker; no public upload occurs.

This slice accepts supplied recognized bundles. Image ingestion, actual native OCR, original image
serving, pending/failed inference-job orchestration, CLI/API/browser flows and real model methods are
still separate integration work. Literal synthetic controls do not measure OCR or receipt accuracy.
