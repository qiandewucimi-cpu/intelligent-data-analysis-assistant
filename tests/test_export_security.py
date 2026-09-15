from __future__ import annotations

import unittest

import pandas as pd

from analyzer.columns import OUTLIER_FIELDS_COLUMN, OUTLIER_FLAG_COLUMN
from ui.export_security import escape_spreadsheet_formulas, prepare_cleaned_export_dataframe


class ExportSecurityTests(unittest.TestCase):
    def test_escapes_formula_like_text_without_changing_numbers(self) -> None:
        source = pd.DataFrame(
            {
                "text": ["=cmd()", " +SUM(A1:A2)", "@remote", "normal"],
                "number": [-10, 20, 30, 40],
            }
        )

        safe = escape_spreadsheet_formulas(source)

        self.assertEqual(safe["text"].tolist(), ["'=cmd()", "' +SUM(A1:A2)", "'@remote", "normal"])
        self.assertEqual(safe["number"].tolist(), [-10, 20, 30, 40])
        self.assertEqual(source.iloc[0, 0], "=cmd()")

    def test_cleaned_export_drops_empty_outlier_helper_columns(self) -> None:
        source = pd.DataFrame(
            {
                "销售额": [10, 20],
                OUTLIER_FLAG_COLUMN: [False, False],
                OUTLIER_FIELDS_COLUMN: ["", ""],
            }
        )

        exported = prepare_cleaned_export_dataframe(source)

        self.assertEqual(exported.columns.tolist(), ["销售额"])
        self.assertEqual(source.columns.tolist(), ["销售额", OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN])

    def test_cleaned_export_keeps_outlier_details_when_present(self) -> None:
        source = pd.DataFrame(
            {
                "销售额": [10, 999],
                OUTLIER_FLAG_COLUMN: [False, True],
                OUTLIER_FIELDS_COLUMN: ["", "销售额"],
            }
        )

        exported = prepare_cleaned_export_dataframe(source)

        self.assertIs(exported, source)
        self.assertIn(OUTLIER_FLAG_COLUMN, exported.columns)


if __name__ == "__main__":
    unittest.main()
