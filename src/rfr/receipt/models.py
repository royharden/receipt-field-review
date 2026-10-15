"""Receipt-local composite schema; no extra shared-module or provider wire ownership."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from ..shared.docio.models import OpaqueId, Sha256, Wire
from ..shared.fieldextract.models import FieldValue

SCALARS = ("merchant_name", "date", "currency", "subtotal", "tax", "total", "payment_method")
LINE_CELLS = ("description", "quantity", "unit_price", "amount")
# Factual subset checked against SIX list-one.xml Pblshd2026-09-17 on2026-10-15.
# Source: https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml
MINOR_UNITS = {"USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2, "JPY": 0, "KWD": 3}


class CurrencyPolicy(Wire):
    code: Literal["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "KWD"] = "USD"
    decimal_separator: Literal[".", ","] = "."
    group_separator: Literal[".", ",", " "] | None = ","
    version: Literal["receipt-currency/1"] = "receipt-currency/1"

    @model_validator(mode="after")
    def separators_differ(self) -> Self:
        if self.group_separator == self.decimal_separator:
            raise ValueError("decimal and group separators must differ")
        return self

    @property
    def minor_units(self) -> int:
        return MINOR_UNITS[self.code]


class ReceiptContext(Wire):
    currency: CurrencyPolicy
    reference_date: date | None
    policy_version: Literal["receipt-checks/1"] = "receipt-checks/1"


class ReceiptLine(Wire):
    row_key: OpaqueId
    cells: dict[str, FieldValue]

    @model_validator(mode="after")
    def complete_cells(self) -> Self:
        if set(self.cells) != set(LINE_CELLS):
            raise ValueError("all four line-cell metadata records required")
        for key, field in self.cells.items():
            if field.field_id != f"line:{self.row_key}:{key}":
                raise ValueError("line-cell field identity mismatch")
        return self


class PrintedAdjustment(Wire):
    adjustment_id: OpaqueId
    kind: Literal["tip", "service", "discount"]
    stage: Literal["before_subtotal", "after_subtotal", "unknown"]
    amount: FieldValue

    @model_validator(mode="after")
    def amount_identity(self) -> Self:
        if self.amount.field_id != f"adjustment:{self.adjustment_id}":
            raise ValueError("adjustment field identity mismatch")
        return self


class CheckResult(Wire):
    check_id: OpaqueId
    status: Literal["pass", "fail", "not_checkable"]
    field_ids: tuple[OpaqueId, ...]
    reason: OpaqueId | None

    @model_validator(mode="after")
    def explicit_reason(self) -> Self:
        if (self.status == "pass") != (self.reason is None):
            raise ValueError("failed/not-checkable code check needs a reason")
        return self


class Receipt(Wire):
    receipt_id: OpaqueId
    document_id: OpaqueId
    raw_source_revision: OpaqueId
    artifact_sha256: Sha256
    context: ReceiptContext
    fields: dict[str, FieldValue]
    line_items: tuple[ReceiptLine, ...] = Field(max_length=200)
    adjustments: tuple[PrintedAdjustment, ...] = Field(max_length=20)
    checks: tuple[CheckResult, ...] = ()

    @model_validator(mode="after")
    def complete_fixed_schema(self) -> Self:
        if set(self.fields) != set(SCALARS):
            raise ValueError("complete fixed scalar metadata required")
        if any(value.field_id != key for key, value in self.fields.items()):
            raise ValueError("scalar field identity mismatch")
        rows = tuple(row.row_key for row in self.line_items)
        ids = tuple(item.adjustment_id for item in self.adjustments)
        if len(set(rows)) != len(rows) or len(set(ids)) != len(ids):
            raise ValueError("duplicate receipt row/adjustment identity")
        return self

    def all_fields(self) -> tuple[FieldValue, ...]:
        return (
            *self.fields.values(),
            *(cell for row in self.line_items for cell in row.cells.values()),
            *(adjustment.amount for adjustment in self.adjustments),
        )
