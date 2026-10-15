# Canonical offline execution components

`rfr.shared.execution` contains the unchanged published S3 provider/call-ledger closure and S6
screening closure as sibling modules. All screening and provider calls use the same native request,
ledger and budget classes; the earlier S6 ledger copy is not included. The purpose-fixed S3 ledger
is the sole implementation. Source commits, exact Git blob hashes and MIT notices are in SOURCE.json.

These components currently support mock, strict replay and injected simulation. Synthetic captures
retain mock origin. They do not install a live SDK or authorize a paid call, empirical calibration or
source-currentness claim. Receipt persistence must atomically check the actual generation.

Public conformance inputs are retained byte-for-byte as `.py.txt` assets. The isolation control
materializes every supplied test, schema, script and synthetic price input under a temporary root,
maps test imports and necessary test paths explicitly, and records original/adapted hashes and diffs.
It blocks original app/SDK imports and network access and checks canonical class identity. These are
implementation controls, not independent receipt data, human Gold or finished-app acceptance.
