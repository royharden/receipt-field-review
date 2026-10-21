# Optional local image HTTP host

The application factory accepts trusted `enable_images=True` and an optional server-created
`ImageWorker`; the default recognized-only factory keeps image capabilities disabled. No client
wire configures executable/model paths. `image_upload` describes available staging; `local_b0`
additionally requires configured engine files. HEIC without its optional codec refuses explicitly.
No automatic installation, model/provider fallback or receipt-quality claim is supplied.

All routes retain exact loopback Host, capability, mutation Origin, fetch-site, duplicate-header
and private-response controls. Only `PUT /api/batches/{batch_id}/images/{original_sha256}` admits
`application/octet-stream`: at most 20 MiB encoded, 1024 ASGI body messages and the configured body
deadline. Declared and actual lengths must agree. Other mutations keep the configured JSON limit
and its 25 MiB hard ceiling. The path digest must match the complete original before decoding.
Decode retains the existing 25-million-pixel / 80-MiB normalized-output bounds.

Staging returns a strict `StagedImage`, with original identity, original byte count/format,
normalized PNG file digest and dimensions, and `ocr_executed=false`. It is not a registered review
item. The normalized PNG file digest is distinct from the Docio RGBA8 grid digest used by review
image responses. Exact valid retained retries return 200 without decoding; new retention returns
201. Partial/changed output is preserved and refused. No original container/metadata is served.

The HTTP host limits the union of staged identities and registered items, including tombstones and
partial image directories, to 100 per batch. It serializes staging and recognized imports while
enabled, rechecks capacity before publication and rejects a second upload or new job while busy.
Partial directories consume capacity. There is no automatic deletion or age cleanup. Files are
owner-local: an external CLI/process that ignores this host's ownership is not a supported concurrent
writer, and no hostile multiuser isolation or workspace-wide disk quota is claimed.

`POST /api/batches/{batch_id}/image-jobs` accepts strict `ImageJobStart`, containing a bounded
request ID and the existing `ImageJobSpec`: B0, explicit reference date, 1..100 retained identities,
expected revisions and fixed config profile. Batch currency comes from its manifest. A new accepted
job returns 202; an exact historical request returns 200 without execution, even after failure or
interruption or without a currently configured engine. Changed intent and an active batch job
conflict. The server has one sequential executor without a cross-batch pending queue. Source CAS,
tombstones, journal refusal, retained partial success and the complete fixed cohort remain JobStore
semantics. Only actual persisted success becomes `ok`. Frozen engine/config digests are checked
through preflight, native execution and pre-publication.

`GET /api/batches/{batch_id}/image-jobs/{job_id}` reads the persisted JobRecord. It creates no job
directory, executes nothing and performs no recovery. Lifespan startup takes an exclusive OS-owned
data-root lock; it neither steals ownership by age nor automatically replays pending jobs. Explicit
trusted recovery of an interrupted record requires establishing that its old worker is gone.

Shutdown closes new upload/start admission, waits for an admitted upload, requests stop between image
items and drains the actual executor before releasing the data-root lock. A completed in-flight item
retains its result; remaining queued items become `not_run` with shutdown reason and the job becomes
`interrupted`. There is no daemon escape, concurrent recovery, fabricated terminal result or lock
release while an owned thread survives. Abrupt process death can leave durable pending/running state
for explicit later recovery; it never authorizes replay.

**Lifetime limitation:** image decoding is synchronous native codec code within this process.
Graceful drain can wait indefinitely if a codec hangs. This implementation does not provide a hard
shutdown deadline or process-isolated codec termination. That boundary, real native OCR/HEIC,
browser integration and the approved measured evaluation require separate qualification. Authored
pixels and injected native responses only test control flow and persistence.
