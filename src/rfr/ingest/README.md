# Local image staging

`python -m rfr.ingest --source <file> --out <existing-private-parent>` decodes one PNG, JPEG
or HEIC using the optional pinned Pillow/pillow-heif extras. It writes a private content-addressed
artifact, with exact original bytes, normalized RGB PNG and a final closed manifest. It never
creates a receipt batch, dispatches OCR or changes the decision journal.

Bounds are 20 MiB encoded input, 25 million header/delivered pixels, one image and 80 MiB normalized
PNG output. A caller can narrow these limits, never widen them. Signature and encoded-size checks
precede optional imports; header dimensions and frame count precede pixel loading. Delivered size
is checked again because a native decoder can refine dimensions during load. Native codec internal
allocations and CPU time are not sandboxed here; a future HTTP worker still needs a separate
bounded process, cancellation and lifecycle design before accepting untrusted uploads.

The normalized RGB PNG is the eventual source-page coordinate grid. Alpha is flattened onto white;
color conversion is 8-bit Pillow conversion without a calibrated color-management claim. Derivatives
contain no copied EXIF/XMP/ICC data. Original bytes retain their metadata and stay private.

PNG/JPEG normalization records EXIF orientation and an inverse pair of matrices from the decoder
raster to the normalized page. Coordinates describe pixel boundaries `[0,width] × [0,height]`.
HEIC container transforms are applied inside libheif; its delivered raster is explicitly the starting
grid, with an identity normalization matrix. `container_orientation` retains the plugin's reported
metadata value when present; it does not recover an affine transform from raw encoded container
coordinates. OCR boxes must eventually bind to the normalized page hash and dimensions.

`image-<original-sha256>/` contains only `original.bin`, `page.png`, `manifest.json`. File writes use
exclusive creation and fsync, with the manifest written last. Existing exact complete artifacts are
reused; modified/incomplete output refuses further writes. A partial directory is retained for
diagnosis. The parent uses the existing local mutex and must be owner-controlled; these helpers do
not provide hostile multiuser filesystem isolation or a power-loss directory-fsync guarantee.

Reopening also requires the declared format/grid, EXIF orientation, dimensions and forward/inverse
matrices to describe the same normalization. The normalized PNG's fixed IHDR header, including its
CRC, must agree with the declared dimensions and 8-bit noninterlaced RGB profile. These checks use
the [PNG header and chunk layout](https://www.w3.org/TR/png/#11IHDR) without importing an optional
codec. They reject inconsistent metadata even when file hashes agree; they do not authenticate
the producer, re-decode every pixel or validate every PNG chunk. Refusal preserves all staged bytes.

`tests/ingest/test_images.py` exercises real codecs on authored images, eight JPEG orientations,
HEIC orientation, multipage refusal, malformed signatures/data, pixel/output limits, missing
extras, private staging/reopen, exact retry, hardlink/path refusal and the real local command.
The optional CI job imports both codecs explicitly before running these checks. Local Windows
execution does not prove Linux CI or a Bolt-hosted Python runtime.

This artifact is preliminary image staging, not a recognized `ReceiptBundle` or a new canonical
Docio wire. The existing recognized-bundle workflow remains unchanged. Native OCR, actual image
geometry, image-to-B0/jobs/API/UI integration, held-out evaluation and independent app acceptance
remain separate required work.

Decoder references: [Pillow file lifecycle](https://pillow.readthedocs.io/en/stable/reference/open_files.html),
[Pillow image bounds](https://pillow.readthedocs.io/en/stable/reference/Image.html), and
[pillow-heif orientation/plugin behavior](https://pillow-heif.readthedocs.io/en/stable/pillow-plugin.html).
