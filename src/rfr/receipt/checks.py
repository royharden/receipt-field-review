"""Receipt-local code checks; unknown/missing operands are never zero or successful checks."""

from datetime import date
from decimal import Decimal

from ..shared.fieldextract.models import CheckIssue
from .models import CheckResult, Receipt
from .normalization import (
    decimal_value,
    normalize_date,
    normalize_money,
    normalize_quantity,
    within_minor_unit,
)


def check_receipt(receipt: Receipt, *, effective: bool = False) -> tuple[CheckResult, ...]:
    def value(field):
        return field.value if effective else field.proposal

    def number(field):
        normalized = (
            normalize_quantity(value(field), receipt.context.currency)
            if field.field_id.endswith(":quantity")
            else normalize_money(value(field), receipt.context.currency)
        )
        return decimal_value(normalized.value) if not normalized.issues else None

    results = []

    def arithmetic(name, actual, expected, fields):
        if actual is None or expected is None:
            results.append(
                CheckResult(
                    check_id=name,
                    status="not_checkable",
                    field_ids=tuple(fields),
                    reason="missing_or_invalid_operand",
                )
            )
        else:
            ok = within_minor_unit(actual, expected, receipt.context.currency)
            results.append(
                CheckResult(
                    check_id=name,
                    status="pass" if ok else "fail",
                    field_ids=tuple(fields),
                    reason=None if ok else "arithmetic_mismatch",
                )
            )

    before = []
    after = []
    unknown = False
    for adjustment in receipt.adjustments:
        amount = number(adjustment.amount)
        signed = -abs(amount) if amount is not None and adjustment.kind == "discount" else amount
        if adjustment.stage == "unknown":
            unknown = True
        (before if adjustment.stage == "before_subtotal" else after).append(signed)
    subtotal = number(receipt.fields["subtotal"])
    tax = number(receipt.fields["tax"])
    total = number(receipt.fields["total"])
    amounts = [number(row.cells["amount"]) for row in receipt.line_items]
    sum_rows = (
        sum((*amounts, *before), Decimal(0))
        if amounts and not unknown and all(v is not None for v in (*amounts, *before))
        else None
    )
    arithmetic(
        "line_amounts_equal_subtotal",
        subtotal,
        sum_rows,
        (
            "subtotal",
            *(row.cells["amount"].field_id for row in receipt.line_items),
            *(a.amount.field_id for a in receipt.adjustments if a.stage != "after_subtotal"),
        ),
    )
    expected_total = (
        subtotal + tax + sum(after, Decimal(0))
        if not unknown
        and subtotal is not None
        and tax is not None
        and all(v is not None for v in after)
        else None
    )
    arithmetic(
        "subtotal_tax_adjustments_equal_total",
        total,
        expected_total,
        (
            "subtotal",
            "tax",
            "total",
            *(a.amount.field_id for a in receipt.adjustments if a.stage != "before_subtotal"),
        ),
    )
    for row in receipt.line_items:
        quantity = number(row.cells["quantity"])
        unit = number(row.cells["unit_price"])
        amount = number(row.cells["amount"])
        expected = quantity * unit if quantity is not None and unit is not None else None
        arithmetic(
            "quantity_times_unit_price:" + row.row_key,
            amount,
            expected,
            tuple(row.cells[name].field_id for name in ("quantity", "unit_price", "amount")),
        )
    raw_date = value(receipt.fields["date"])
    normalized = normalize_date(raw_date, receipt.context.reference_date)
    if normalized.value is None or receipt.context.reference_date is None:
        results.append(
            CheckResult(
                check_id="valid_nonfuture_date",
                status="not_checkable",
                field_ids=("date",),
                reason="missing_invalid_or_ambiguous_date",
            )
        )
    else:
        future = date.fromisoformat(normalized.value) > receipt.context.reference_date
        results.append(
            CheckResult(
                check_id="valid_nonfuture_date",
                status="fail" if future else "pass",
                field_ids=("date",),
                reason="future_date" if future else None,
            )
        )
    currency = value(receipt.fields["currency"])
    if currency is None:
        results.append(
            CheckResult(
                check_id="printed_batch_currency",
                status="not_checkable",
                field_ids=("currency",),
                reason="printed_currency_unavailable",
            )
        )
    else:
        ok = currency == receipt.context.currency.code
        results.append(
            CheckResult(
                check_id="printed_batch_currency",
                status="pass" if ok else "fail",
                field_ids=("currency",),
                reason=None if ok else "currency_mismatch",
            )
        )
    return tuple(results)


def check_issues(results: tuple[CheckResult, ...]) -> tuple[CheckIssue, ...]:
    return tuple(
        CheckIssue(
            issue_id=result.check_id + ":" + result.reason,
            severity="hard_failure" if result.status == "fail" else "review",
            field_ids=result.field_ids,
        )
        for result in results
        if result.status != "pass"
    )
