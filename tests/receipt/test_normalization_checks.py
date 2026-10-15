"""Exact-money and missing-operand/ambiguity controls, not receipt accuracy measurements."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from rfr.receipt.checks import check_issues, check_receipt
from rfr.receipt.models import (
    CurrencyPolicy,
    PrintedAdjustment,
    Receipt,
    ReceiptContext,
    ReceiptLine,
)
from rfr.receipt.normalization import (
    normalize_currency,
    normalize_date,
    normalize_money,
    normalize_quantity,
    within_minor_unit,
)
from rfr.shared.fieldextract.models import FieldValue, ScoreComponents


def field(name, value):
    return FieldValue(
        field_id=name,
        value=None,
        confidence=None,
        source=None,
        method="synthetic-control",
        status="needs_review",
        proposal=value,
        human_provenance_ref=None,
        hard_flags=(),
        issues=(),
        components=ScoreComponents(
            selector_probability=None,
            verifier_probability=None,
            native_quality_multiplier=None,
            native_quality_policy=None,
        ),
        score_version="synthetic/1",
        threshold_version="uncalibrated/1",
    )


def receipt(**changes):
    values = {
        "merchant_name": "SYNTHETIC SHOP",
        "date": "2026-10-14",
        "currency": "USD",
        "subtotal": "6.00",
        "tax": "0.60",
        "total": "6.60",
        "payment_method": None,
    }
    values |= changes
    line = ReceiptLine(
        row_key="row:0",
        cells={
            key: field("line:row:0:" + key, value)
            for key, value in {
                "description": "Coffee",
                "quantity": "2",
                "unit_price": "3.00",
                "amount": "6.00",
            }.items()
        },
    )
    return Receipt(
        receipt_id="synthetic-receipt",
        document_id="synthetic-doc",
        raw_source_revision="synthetic-control-no-original-image",
        artifact_sha256="a" * 64,
        context=ReceiptContext(currency=CurrencyPolicy(), reference_date=date(2026, 10, 14)),
        fields={key: field(key, value) for key, value in values.items()},
        line_items=(line,),
        adjustments=(),
    )


@pytest.mark.parametrize(
    "raw,policy,expected",
    [
        ("$1,234.50", CurrencyPolicy(), "1234.50"),
        ("(USD 2.00)", CurrencyPolicy(), "-2.00"),
        ("$-2.00", CurrencyPolicy(), "-2.00"),
        ("0", CurrencyPolicy(), "0.00"),
        (
            "1.234,56",
            CurrencyPolicy(code="EUR", decimal_separator=",", group_separator="."),
            "1234.56",
        ),
        ("JPY 1234", CurrencyPolicy(code="JPY"), "1234"),
        ("KWD 1.234", CurrencyPolicy(code="KWD"), "1.234"),
    ],
    ids=[
        "grouped",
        "refund-parentheses",
        "negative",
        "zero",
        "comma-locale",
        "zero-minor",
        "three-minor",
    ],
)
def test_exact_money_preserves_sign_zero_and_configured_minor_units(raw, policy, expected):
    result = normalize_money(raw, policy)
    assert result.value == expected and result.issues == ()


@pytest.mark.parametrize(
    "raw",
    [
        True,
        1.23,
        "NaN",
        "Infinity",
        "1e3",
        "1,23.00",
        "1.234",
        "--2.00",
        "(-2.00)",
        "€1.00",
        "USD USD 2.00",
        "1.",
        "",
        None,
    ],
)
def test_invalid_money_never_rounds_or_accepts_float_bool_or_currency_mismatch(raw):
    result = normalize_money(raw, CurrencyPolicy())
    assert result.value is None and result.issues


def test_one_minor_unit_inclusive_boundary_and_no_binary_float_operand():
    policy = CurrencyPolicy()
    assert within_minor_unit(Decimal("1.01"), Decimal("1"), policy)
    assert not within_minor_unit(Decimal("1.0100001"), Decimal("1"), policy)
    assert within_minor_unit(Decimal("-1.01"), Decimal("-1"), policy)
    with pytest.raises(ValueError):
        within_minor_unit(1.01, Decimal("1"), policy)
    with pytest.raises(ValueError):
        within_minor_unit(Decimal("NaN"), Decimal("1"), policy)


def test_printed_currency_is_not_manufactured_from_batch_context_or_symbol():
    policy = CurrencyPolicy()
    assert normalize_currency("usd", policy).value == "USD"
    assert normalize_currency("$", policy).value is None
    assert normalize_currency("EUR", policy).issues == ("currency_mismatch",)
    assert normalize_currency(None, policy).value is None
    assert normalize_currency("XYZ", policy).value is None
    with pytest.raises(ValidationError):
        CurrencyPolicy(code="XYZ")
    with pytest.raises(ValidationError):
        CurrencyPolicy(decimal_separator=",", group_separator=",")


def test_quantity_is_printed_exact_decimal_and_never_default_one():
    assert normalize_quantity("0.333", CurrencyPolicy()).value == "0.333"
    assert normalize_quantity("-1", CurrencyPolicy()).value == "-1"
    for missing in (None, True, "", "1e3", "1/2"):
        assert normalize_quantity(missing, CurrencyPolicy()).value is None


@pytest.mark.parametrize(
    "raw,expected,issue",
    [
        ("2026-10-14", "2026-10-14", None),
        ("1900-01-01", "1900-01-01", None),
        ("12/31/2025", "2025-12-31", None),
        ("31/12/2025", "2025-12-31", None),
        ("JAN 1, 2026", "2026-01-01", None),
        ("03/04/2026", None, "ambiguous_date"),
        ("2026-10-15", "2026-10-15", "future_date"),
        ("2026-02-30", None, "invalid_date"),
        ("03/04/26", None, "invalid_date"),
    ],
)
def test_explicit_clock_conservative_numeric_dates_and_old_date_allowed(raw, expected, issue):
    result = normalize_date(raw, date(2026, 10, 14))
    assert result.value == expected and result.issues == (() if issue is None else (issue,))
    assert normalize_date("2026-10-14", None).issues == ("reference_date_unavailable",)


def statuses(value):
    return {result.check_id: result.status for result in check_receipt(value)}


def test_complete_printed_arithmetic_date_currency_and_zero_negative_are_actual_code_checks():
    assert set(statuses(receipt()).values()) == {"pass"}
    zero = receipt(subtotal="0.00", tax="0.00", total="0.00")
    line = zero.line_items[0]
    cells = line.cells | {
        "quantity": field("line:row:0:quantity", "0"),
        "amount": field("line:row:0:amount", "0.00"),
    }
    zero = zero.model_copy(update={"line_items": (line.model_copy(update={"cells": cells}),)})
    assert set(statuses(zero).values()) == {"pass"}
    negative = receipt(subtotal="-6.00", tax="-0.60", total="-6.60")
    line = negative.line_items[0]
    cells = line.cells | {
        "quantity": field("line:row:0:quantity", "-2"),
        "amount": field("line:row:0:amount", "-6.00"),
    }
    assert set(
        statuses(
            negative.model_copy(update={"line_items": (line.model_copy(update={"cells": cells}),)})
        ).values()
    ) == {"pass"}


def test_missing_tax_quantity_or_amount_is_not_checkable_never_zero_or_guessed_one():
    assert statuses(receipt(tax=None))["subtotal_tax_adjustments_equal_total"] == "not_checkable"
    original = receipt()
    line = original.line_items[0]
    for key in ("quantity", "unit_price", "amount"):
        row = line.model_copy(
            update={"cells": line.cells | {key: field("line:row:0:" + key, None)}}
        )
        checked = statuses(original.model_copy(update={"line_items": (row,)}))
        assert checked["quantity_times_unit_price:row:0"] == "not_checkable"
        if key == "amount":
            assert checked["line_amounts_equal_subtotal"] == "not_checkable"
    assert (
        statuses(receipt(subtotal="6.001"))["subtotal_tax_adjustments_equal_total"]
        == "not_checkable"
    )


def test_explicit_tip_service_discount_stages_and_unknown_stage_no_wider_tolerance():
    original = receipt(total="8.10")
    adjustments = tuple(
        PrintedAdjustment(
            adjustment_id=key,
            kind=kind,
            stage="after_subtotal",
            amount=field("adjustment:" + key, value),
        )
        for key, kind, value in [
            ("tip", "tip", "2.00"),
            ("service", "service", "0.50"),
            ("discount", "discount", "1.00"),
        ]
    )
    with_adjustments = original.model_copy(update={"adjustments": adjustments})
    assert statuses(with_adjustments)["subtotal_tax_adjustments_equal_total"] == "pass"
    wrong = with_adjustments.model_copy(
        update={"fields": with_adjustments.fields | {"total": field("total", "8.12")}}
    )
    assert statuses(wrong)["subtotal_tax_adjustments_equal_total"] == "fail"
    unknown = with_adjustments.model_copy(
        update={"adjustments": (adjustments[0].model_copy(update={"stage": "unknown"}),)}
    )
    assert statuses(unknown)["subtotal_tax_adjustments_equal_total"] == "not_checkable"


def test_missing_or_wrong_fixed_cell_schema_and_duplicate_rows_refuse():
    original = receipt()
    raw = original.model_dump()
    raw["fields"].pop("currency")
    with pytest.raises(ValidationError):
        Receipt.model_validate(raw)
    raw = original.model_dump()
    raw["line_items"][0]["cells"].pop("quantity")
    with pytest.raises(ValidationError):
        Receipt.model_validate(raw)
    raw = original.model_dump()
    raw["line_items"] *= 2
    with pytest.raises(ValidationError):
        Receipt.model_validate(raw)
    bad = receipt(total="99.00")
    issues = check_issues(check_receipt(bad))
    assert any(i.severity == "hard_failure" and "total" in i.field_ids for i in issues)


def test_before_subtotal_adjustment_is_not_added_twice_and_partial_rows_do_not_disappear():
    original = receipt(subtotal="5.00", tax="0.50", total="5.50")
    discount = PrintedAdjustment(
        adjustment_id="coupon",
        kind="discount",
        stage="before_subtotal",
        amount=field("adjustment:coupon", "1.00"),
    )
    adjusted = original.model_copy(update={"adjustments": (discount,)})
    assert statuses(adjusted)["line_amounts_equal_subtotal"] == "pass"
    assert statuses(adjusted)["subtotal_tax_adjustments_equal_total"] == "pass"
    missing_line = ReceiptLine(
        row_key="row:missing",
        cells={
            key: field("line:row:missing:" + key, None)
            for key in ("description", "quantity", "unit_price", "amount")
        },
    )
    partial = adjusted.model_copy(update={"line_items": (*adjusted.line_items, missing_line)})
    assert statuses(partial)["line_amounts_equal_subtotal"] == "not_checkable"
