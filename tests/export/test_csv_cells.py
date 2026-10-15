"""Spreadsheet-active text is escaped while private JSON retains original values."""

import pytest

from rfr.export.receipt import csv_text, write_export


@pytest.mark.parametrize(
    "value", ["=1+1", "+cmd", "-1.00", "@A1", "  =1", "\ttext", "\rtext", "\ntext"]
)
def test_formula_and_control_leading_cells_are_text(value):
    assert csv_text(value) == "'" + value


def test_plain_text_and_null_not_changed_and_export_names_closed(tmp_path):
    assert csv_text("ordinary") == "ordinary" and csv_text(None) == ""
    with pytest.raises(ValueError):
        write_export(tmp_path, {"../outside": b"control"})
