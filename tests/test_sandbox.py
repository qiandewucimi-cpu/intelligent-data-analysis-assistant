from __future__ import annotations

import unittest

import pandas as pd

from analyzer.executor import run_in_sandbox, validate_code_safety
from analyzer.sandbox_worker import _normalize_result


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["华东", "华北", "华东", "华南", "华北"],
            "sales": [100, 200, 150, 50, 300],
        }
    )


class SandboxValidationTests(unittest.TestCase):
    def test_rejects_file_read_import_and_dunder(self) -> None:
        for code in (
            "import os\nresult = os.listdir('.')",
            "result = pd.read_csv('.env')",
            "result = df.__class__",
            "module = pd\nresult = module.read_csv('.env')",
        ):
            with self.assertRaises(ValueError):
                validate_code_safety(code)

    def test_reject_is_reported_without_spawning_a_process(self) -> None:
        result = run_in_sandbox("import os\nresult = os.listdir('.')", _sample_frame())
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "rejected")


class SandboxExecutionTests(unittest.TestCase):
    def test_groupby_result_matches_direct_pandas(self) -> None:
        code = (
            "result = df.groupby('region', as_index=False)['sales'].sum()"
            ".sort_values('sales', ascending=False)"
        )
        result = run_in_sandbox(code, _sample_frame())
        self.assertTrue(result.ok, result.error)

        # The contract: sandbox output == direct pandas + the documented
        # result normalization (a permuted unnamed index surfaces as a column).
        direct = (
            _sample_frame()
            .groupby("region", as_index=False)["sales"]
            .sum()
            .sort_values("sales", ascending=False)
        )
        pd.testing.assert_frame_equal(result.result_frame, _normalize_result(direct))

    def test_input_dtypes_survive_the_boundary(self) -> None:
        # Pickled input keeps dtypes: generated code may still use .dt accessors.
        df = pd.DataFrame(
            {"d": pd.to_datetime(["2024-01-01", "2024-02-01"]), "v": [1, 2]}
        )
        result = run_in_sandbox("result = df['d'].dt.year", df)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.result_frame), 2)

    def test_none_result_becomes_placeholder_frame(self) -> None:
        result = run_in_sandbox("result = None", _sample_frame())
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.result_frame.columns.tolist(), ["结果"])

    def test_error_inside_code_is_reported_not_raised(self) -> None:
        result = run_in_sandbox("result = df['missing_column'].sum()", _sample_frame())
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "error")
        self.assertIn("missing_column", result.error)


class SandboxResourceLimitTests(unittest.TestCase):
    def test_timeout_kills_runaway_code(self) -> None:
        code = "result = sum(i for i in range(10**9))"
        result = run_in_sandbox(code, _sample_frame(), timeout_s=1.0)
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "timeout")

    def test_memory_limit_kills_allocation(self) -> None:
        code = (
            "chunks = []\n"
            "for i in range(1000):\n"
            "    chunks.append([0] * 10**7)\n"
            "result = len(chunks)"
        )
        result = run_in_sandbox(code, _sample_frame(), timeout_s=30.0, memory_mb=512)
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "memory")


if __name__ == "__main__":
    unittest.main()
