from __future__ import annotations

import unittest

import pandas as pd

from utils.export_security import escape_spreadsheet_formulas


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


if __name__ == "__main__":
    unittest.main()
