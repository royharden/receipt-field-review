"""Source-backed literal receipt controls; no native image/real-data/model accuracy claim."""

import hashlib
from datetime import date

import pytest

from rfr.receipt.b0 import extract_b0
from rfr.receipt.candidates import build_bank
from rfr.receipt.models import CurrencyPolicy, ReceiptContext
from rfr.shared.docio.identity import artifact_bytes, grid_digest, raw_revision
from rfr.shared.docio.models import Bounds, Document, PageInput, Provenance
from rfr.shared.docio.tsv import HEADER, page_from_artifact, parse_tsv_artifact


def literal_receipt(lines=None):
    text = lines or [
        "Merchant: SYNTHETIC SHOP",
        "DATE 2026-10-14",
        "CURRENCY USD",
        "Coffee 2 x 3.00 6.00",
        "Cake 4.00",
        "SUBTOTAL 10.00",
        "TAX 1.00",
        "TIP 2.00",
        "SERVICE 0.50",
        "DISCOUNT 1.00",
        "TOTAL 12.50",
        "VISA",
    ]
    width, height = 500, max(400, len(text) * 20 + 40)
    original = hashlib.sha256(b"literal control, not an encoded receipt image").hexdigest()
    revision = raw_revision("literal-doc", original)
    grid = grid_digest(width, height, b"\xff\xff\xff\xff" * (width * height))
    inp = PageInput.model_validate(
        {
            "execution_ref": "literal-private-handle",
            "document_id": "literal-doc",
            "original_content_sha256": original,
            "raw_source_revision": revision,
            "page_id": "page:0",
            "page_index": 0,
            "page_sha256": grid,
            "width_px": width,
            "height_px": height,
            "grid_policy_id": "rgba8-source-grid-v1",
            "source_kind": "image",
            "transforms": {
                "source_to_engine": {
                    "direction": "source_to_engine",
                    "algorithm": "identity/1",
                    "matrix": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                },
                "engine_to_source": {
                    "direction": "engine_to_source",
                    "algorithm": "identity/1",
                    "matrix": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                },
            },
        }
    )
    rows = [
        f"1\t1\t0\t0\t0\t0\t0\t0\t{width}\t{height}\t-1\t",
        f"2\t1\t1\t0\t0\t0\t0\t0\t{width}\t{height}\t-1\t",
        f"3\t1\t1\t1\t0\t0\t0\t0\t{width}\t{height}\t-1\t",
    ]
    for index, line in enumerate(text, 1):
        top = index * 20
        rows.extend(
            [
                f"4\t1\t1\t1\t{index}\t0\t10\t{top}\t450\t15\t-1\t",
                f"5\t1\t1\t1\t{index}\t1\t10\t{top}\t450\t15\t98\t{line}",
            ]
        )
    tsv = HEADER + b"\n" + ("\n".join(rows) + "\n").encode()
    bounds = Bounds(
        max_pages=1,
        max_encoded_bytes=1024 * 1024,
        max_decoded_pixels=width * height,
        max_words=100,
        max_lines=100,
        max_blocks=10,
        max_output_bytes=1024 * 1024,
        deadline_s=2.0,
    )
    artifact = parse_tsv_artifact(
        tsv,
        inp,
        bounds,
        engine_width_px=width,
        engine_height_px=height,
        engine_version="synthetic-format-control/1",
        config_sha256="a" * 64,
    )
    recognized = page_from_artifact(artifact, inp)
    document = Document(
        document_id=inp.document_id,
        original_content_sha256=original,
        raw_source_revision=revision,
        source_kind="image",
        pages=(recognized,),
        provenance=Provenance(
            producer="literal-control",
            version="synthetic/1",
            config_sha256="a" * 64,
            source_grid_profile="rgba8-source-grid-v1",
        ),
    )
    data = artifact_bytes(artifact)
    return document, artifact, data, hashlib.sha256(data).hexdigest()


def context():
    return ReceiptContext(currency=CurrencyPolicy(), reference_date=date(2026, 10, 14))


def test_full_scalar_line_cells_explicit_adjustments_and_blank_review_default():
    document, artifact, data, digest = literal_receipt()
    result = extract_b0(document, data, digest, context())
    assert set(result.fields) == {
        "merchant_name",
        "date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "payment_method",
    }
    assert result.fields["merchant_name"].proposal == "SYNTHETIC SHOP"
    assert (
        result.fields["total"].proposal == "12.50" and result.fields["currency"].proposal == "USD"
    )
    assert len(result.line_items) == 2 and len(result.adjustments) == 3
    coffee, cake = result.line_items
    assert (
        coffee.cells["quantity"].proposal == "2" and coffee.cells["unit_price"].proposal == "3.00"
    )
    assert cake.cells["quantity"].proposal is None and cake.cells["unit_price"].proposal is None
    assert cake.cells["amount"].proposal == "4.00" and cake.cells["description"].proposal == "Cake"
    assert all(
        field.value is None and field.status in ("needs_review", "abstained")
        for field in result.all_fields()
    )
    checks = {check.check_id: check.status for check in result.checks}
    assert (
        checks["line_amounts_equal_subtotal"]
        == checks["subtotal_tax_adjustments_equal_total"]
        == "pass"
    )
    assert checks["quantity_times_unit_price:" + cake.row_key] == "not_checkable"
    bank = build_bank(document, artifact, digest, context())
    again = build_bank(document, artifact, digest, context())
    assert bank == again
    assert all(
        field.source is not None for field in result.all_fields() if field.proposal is not None
    )


def test_symbol_currency_is_review_only_and_batch_context_is_not_printed_code():
    document, _, data, digest = literal_receipt(
        [
            "ACME SHOP",
            "DATE 2026-10-14",
            "Coffee $3.00",
            "SUBTOTAL $3.00",
            "TAX $0.00",
            "TOTAL $3.00",
        ]
    )
    result = extract_b0(document, data, digest, context())
    assert result.fields["currency"].proposal is None and result.fields["currency"].value is None
    assert "symbol_only_currency" in result.fields["currency"].hard_flags
    assert result.fields["total"].proposal == "3.00"


def test_changed_artifact_hash_or_document_page_fails_before_candidates():
    document, artifact, data, digest = literal_receipt()
    with pytest.raises(ValueError, match="hash mismatch"):
        extract_b0(document, data + b" ", digest, context())
    bad = document.model_copy(
        update={"pages": (document.pages[0].model_copy(update={"processing_ref": "foreign"}),)}
    )
    with pytest.raises(ValueError, match="artifact_page_mismatch"):
        build_bank(bad, artifact, digest, context())


def test_ambiguous_future_dates_missing_tax_and_bad_arithmetic_remain_explicit_failures():
    for printed_date in ("03/04/2026", "2026-10-15"):
        document, _, data, digest = literal_receipt(
            [
                "ACME SHOP",
                "DATE " + printed_date,
                "CURRENCY USD",
                "Coffee 3.00",
                "SUBTOTAL 3.00",
                "TOTAL 99.00",
            ]
        )
        result = extract_b0(document, data, digest, context())
        assert result.fields["date"].status == "needs_review"
        assert ("ambiguous_date" if "/" in printed_date else "future_date") in result.fields[
            "date"
        ].hard_flags
        assert result.fields["tax"].proposal is None
        assert (
            next(
                c for c in result.checks if c.check_id == "subtotal_tax_adjustments_equal_total"
            ).status
            == "not_checkable"
        )


def test_repeated_consistent_printed_currency_is_not_different_currency_or_invented_context():
    document, _, data, digest = literal_receipt(
        [
            "ACME SHOP",
            "DATE 2026-10-14",
            "CURRENCY USD",
            "Coffee USD 3.00",
            "SUBTOTAL USD 3.00",
            "TAX USD 0.00",
            "TOTAL USD 3.00",
        ]
    )
    result = extract_b0(document, data, digest, context())
    assert result.fields["currency"].proposal == "USD"
    assert "ambiguous_candidates" not in result.fields["currency"].hard_flags
    assert result.fields["currency"].value is None


def test_candidate_overflow_refuses_without_truncating_retained_hard_cases():
    document, artifact, data, digest = literal_receipt(["TAX 1.00"] * 64)
    with pytest.raises(ValueError, match="receipt_candidate_overflow"):
        build_bank(document, artifact, digest, context())
    assert len(document.pages[0].lines) == 64 and len(artifact.lines) == 64
    assert hashlib.sha256(data).hexdigest() == digest
