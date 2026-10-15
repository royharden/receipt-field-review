# Synthetic recognized receipt

`provisional-recognized-receipt.json` is an agent-authored implementation control, licensed under
the repository's MIT license. It contains recognized text and a fully bound retained TSV artifact,
not a receipt photograph, an OCR capture or a human-labelled dataset.

It was generated using the existing literal TSV control in
`tests/receipt/test_b0_candidate_plugin.py` and the product's Docio parser and `extract_b0`.
The demo loads only this shipped JSON and product modules; it never imports the tests.
Word positions, page-grid identity and confidence values are authored. A schema's spatial-provenance
tag does not authenticate measured geometry. No original encoded image is supplied or implied.

The text deliberately prints `TOTAL 99.00` against inconsistent operands. The missing cake quantity
and unit price remain unknown. All proposals start in review. The demo records explicit provisional
absence/issue waivers to illustrate operational export without pretending that the arithmetic was
verified or that the agent is a human reviewer. Original machine proposals and issue evidence remain
in the JSONL audit. Synthetic review decisions must not be promoted to independent human Gold.

The demo pins the exact file SHA-256 and refuses changed fixture bytes. The tests verify that pin,
block provider/native imports and sockets, and inspect durable correction replay and export contents.
