# Local native OCR adapter

`TesseractOcr` consumes a staged image and implements the existing `docio.interfaces.OcrAdapter`
contract. `rfr.ingest.native.import_image` joins its result to the unchanged Docio TSV parser,
receipt B0 extractor, ReceiptBundle, BatchStore and rulings journal. There is one authoritative
receipt store and journal. The provided-bundle CLI remains usable without optional codecs.

The normalized PNG is decoded to the canonical displayed RGBA8 grid digest. OCR runs on those
normalized pixels with identity engine/source transforms; original EXIF is not applied twice.
Exact original bytes, normalized PNG bytes, grid identity, actual TSV, processing artifact and
machine bundle retain separate declared hashes. Word geometry/confidence comes from native TSV.
Engine names and valid metadata alone are not native execution evidence.

The trusted operator supplies the installed executable and model directory. The initial adapter
uses English, OEM 1 and PSM 6. It pins the executable, sibling Windows DLL inventory, English model,
TSV configuration, version output and available engine notice; it rechecks executable/model/library/
configuration hashes after execution. A sibling-file inventory is not a loaded-module attestation.
Installed model source/licence provenance remains explicitly unverified. No native binaries/models
are copied into this repository. See [third-party provenance](../../../docs/THIRD-PARTY.md).

The default OCR/probe/parser budget is 30 seconds, with a maximum of 60 for trusted callers.
Version probing and OCR consume the same remaining budget; it is never reset between stages.
The initial extra 10-second probe cutoff was removed after a native timeout and a failing slow-start
control; the overall 30-second default and existing workflow test deadlines are unchanged.
A single child is invoked without a shell; stdout is capped at
4 MiB, stderr at 16 KiB. The child receives required OS paths and private temporary paths, with
one OpenMP thread and no inherited provider credentials. Output-limit, nonzero, missing-engine,
timeout and malformed TSV outcomes refuse successful recognition. Child exit, PID and cleanup
state are recorded; an incomplete cleanup remains a failure. This is a trusted local executable
boundary, not a hostile-executable sandbox or a decoder allocation/CPU bound.

Before native dispatch the app refuses a known full/deleted/stale/unclean batch. BatchStore repeats
the authoritative registration checks atomically. Failed recognition leaves existing receipt heads,
journal bytes and source artifacts intact; new private diagnostic artifacts may remain. Native
`execution.json` describes OCR only. `import.json` describes registration; its absence denotes an
incomplete/refused assembly, and a registration exception is recorded as failed or unknown rather
than asserting no durable effect. Restart never automatically resumes inference.

`tests/ports/test_tesseract_process.py` uses real bounded Python workers for process failures and
environment controls. `tests/ingest/test_native.py` separates injected synthetic fault controls
from an explicit installed-engine functional case. The latter requires `RFR_TEST_TESSERACT`,
`RFR_TEST_TESSDATA` and `RFR_TEST_FONT` pointing at local installed files. It generates authored
pixels, exercises the public CLI and preserves provisional review/retry/rerun/export state. Those
results are native functional evidence, not real-receipt quality or engine selection. The first
native version-probe timeout remains retained alongside later passing controls; stable startup
timing has not been established.

The original-image HTTP/UI join, durable image-job worker, preprocessing beyond normalization,
lawful real-dev engine comparison, live methods, reusable native-adapter export closure and full
application acceptance remain pending. Official [Tesseract CLI/TSV documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
describes the consumed engine format.
