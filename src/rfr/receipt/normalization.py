"""Finite exact decimals and conservative dates/currency; no locale, tax or quantity guesses."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .models import MINOR_UNITS, CurrencyPolicy


@dataclass(frozen=True)
class Normalized:
    value: str | None
    issues: tuple[str, ...] = ()


def normalize_money(raw: object, policy: CurrencyPolicy) -> Normalized:
    if type(raw) is not str or not raw.strip() or len(raw.encode("utf-8")) > 64:
        return Normalized(None, ("invalid_money",))
    text = raw.strip().replace("\u00a0", " ")
    codes = re.findall(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", text)
    if codes:
        if len(codes) != 1:
            return Normalized(None, ("duplicate_currency_token",))
        if any(code != policy.code for code in codes):
            return Normalized(None, ("currency_mismatch",))
        text = re.sub(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", "", text).strip()
    for symbol, allowed in {
        "$": {"USD", "CAD", "AUD"},
        "€": {"EUR"},
        "£": {"GBP"},
        "¥": {"JPY"},
    }.items():
        if symbol in text:
            if policy.code not in allowed:
                return Normalized(None, ("currency_mismatch",))
            if text.count(symbol) != 1:
                return Normalized(None, ("invalid_money",))
            text = text.replace(symbol, "").strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    sign = ""
    if text.startswith(("+", "-")):
        if negative:
            return Normalized(None, ("invalid_money",))
        sign, text = text[0], text[1:]
    parts = text.split(policy.decimal_separator)
    if len(parts) > 2:
        return Normalized(None, ("invalid_money",))
    integer = parts[0]
    if policy.group_separator and policy.group_separator in integer:
        groups = integer.split(policy.group_separator)
        if not (1 <= len(groups[0]) <= 3 and all(len(group) == 3 for group in groups[1:])):
            return Normalized(None, ("invalid_money_grouping",))
        integer = "".join(groups)
    fraction = parts[1] if len(parts) == 2 else ""
    if (
        not re.fullmatch(r"[0-9]{1,18}", integer)
        or fraction
        and not re.fullmatch(r"[0-9]+", fraction)
    ):
        return Normalized(None, ("invalid_money",))
    if len(parts) == 2 and (not fraction or len(fraction) > policy.minor_units):
        return Normalized(None, ("invalid_minor_unit_precision",))
    try:
        amount = Decimal(
            ("-" if negative else sign) + integer + ("." + fraction if fraction else "")
        )
        quantum = Decimal(1).scaleb(-policy.minor_units)
        return Normalized(format(amount.quantize(quantum), "f"))
    except InvalidOperation:
        return Normalized(None, ("invalid_money",))


def normalize_quantity(raw: object, policy: CurrencyPolicy) -> Normalized:
    if type(raw) is not str or len(raw) > 24:
        return Normalized(None, ("invalid_quantity",))
    text = raw.strip().replace(policy.decimal_separator, ".")
    if not re.fullmatch(r"[+-]?[0-9]{1,12}(?:\.[0-9]{1,6})?", text):
        return Normalized(None, ("invalid_quantity",))
    return Normalized(format(Decimal(text), "f"))


def normalize_currency(raw: object, policy: CurrencyPolicy) -> Normalized:
    if type(raw) is not str:
        return Normalized(None, ("unprinted_currency",))
    text = raw.strip().upper()
    if text in MINOR_UNITS:
        return Normalized(text, () if text == policy.code else ("currency_mismatch",))
    if any(symbol in text for symbol in "$€£¥"):
        return Normalized(None, ("symbol_only_currency",))
    return Normalized(None, ("unrecognized_currency",))


MONTHS = {
    name: index
    for index, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1
    )
}


def normalize_date(raw: object, today: date | None) -> Normalized:
    if type(raw) is not str or len(raw) > 64:
        return Normalized(None, ("invalid_date",))
    text = raw.strip().upper()
    parsed = None
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
            parsed = date.fromisoformat(text)
        else:
            numeric = re.fullmatch(r"([0-9]{1,2})[/-]([0-9]{1,2})[/-]([0-9]{4})", text)
            named = re.fullmatch(r"([A-Z]{3})[ .-]+([0-9]{1,2}),? *([0-9]{4})", text)
            if numeric:
                first, second, year = map(int, numeric.groups())
                if first <= 12 and second <= 12 and first != second:
                    return Normalized(None, ("ambiguous_date",))
                month, day = (first, second) if second > 12 or first == second else (second, first)
                parsed = date(year, month, day)
            elif named and named[1] in MONTHS:
                parsed = date(int(named[3]), MONTHS[named[1]], int(named[2]))
    except ValueError:
        return Normalized(None, ("invalid_date",))
    if parsed is None:
        return Normalized(None, ("invalid_date",))
    if today is None:
        return Normalized(parsed.isoformat(), ("reference_date_unavailable",))
    if type(today) is not date:
        raise ValueError("explicit date reference required")
    return Normalized(parsed.isoformat(), ("future_date",) if parsed > today else ())


def decimal_value(value: object) -> Decimal | None:
    if (
        type(value) is not str
        or len(value) > 32
        or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value)
    ):
        return None
    result = Decimal(value)
    return result if result.is_finite() else None


def within_minor_unit(actual: Decimal, expected: Decimal, policy: CurrencyPolicy) -> bool:
    if (
        not isinstance(actual, Decimal)
        or not isinstance(expected, Decimal)
        or not actual.is_finite()
        or not expected.is_finite()
    ):
        raise ValueError("finite exact Decimal operands required")
    return abs(actual - expected) <= Decimal(1).scaleb(-policy.minor_units)
