# Native dependency provenance

The application source uses the root MIT licence. Existing vendored execution components retain
their own source records and notices under `docs/vendor/execution` and `rfr.shared.execution`.
This inventory records observed dependency facts; it does not supply a compatibility or
redistribution decision for a future packaged distribution.

## Optional HEIC wheel

The frozen optional dependency is `pillow-heif==1.8.1`. Its wrapper METADATA names BSD-3-Clause.
The inspected Windows CPython 3.12 binary wheel's `licenses/LICENSES_bundled.txt` instead states
GPLv2 for the binary wheel due to its base libraries. That notice lists libheif and libde265 as
LGPLv3, x265 as GPLv2 and additional Windows runtime notices. Preserve the wrapper/binary
distinction when installing, qualifying or packaging the application. The uv lock pins actual
platform wheel hashes; this observation is specific to the inspected Windows artifact.

The observed bundled-notice SHA-256 is
`7c5eab5b0bc4ed21688891149081b38432b2bbe8e8b49c12708a8ddcf7d700d8`.
Other platforms and future versions require their own notice/provenance inspection. Codec execution
does not establish distribution readiness.

## Installed Tesseract

The local functional control used Tesseract `v5.5.0.20241111` and an installed English model.
The installation's `doc/LICENSE` contains the Apache License 2.0 notice. Native execution records
hash the executable, sibling DLL inventory, model, TSV configuration and available notice, and
retain the actual version/library output. This does not authenticate every loaded library or the
separate model's source/licence provenance. Those qualifications remain explicit limits.

The repository contains no Tesseract executable, native DLL or trained model. Native runtime
installation and any eventual binary/model distribution are separate from the portable Python
source and static frontend. No legal compatibility or clean-distribution claim follows from a
successful local OCR command.
