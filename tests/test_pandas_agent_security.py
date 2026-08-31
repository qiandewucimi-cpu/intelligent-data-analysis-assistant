from __future__ import annotations

import unittest

from utils.pandas_agent import PandasQueryAgent


class PandasAgentSecurityTests(unittest.TestCase):
    def assert_rejected(self, code: str) -> None:
        with self.assertRaises(ValueError):
            PandasQueryAgent._validate_code_safety(code)

    def test_rejects_pandas_file_reads(self) -> None:
        self.assert_rejected("result = pd.read_csv('.env')")
        self.assert_rejected("reader = pd.read_csv\nresult = reader('.env')")
        self.assert_rejected("result = pd.read_pickle('secret.pkl')")

    def test_rejects_numpy_file_reads_and_writes(self) -> None:
        self.assert_rejected("result = np.load('.env')")
        self.assert_rejected("result = np.fromfile('.env')")
        self.assert_rejected("np.save('copy.npy', df)\nresult = df")

    def test_rejects_module_alias_bypass(self) -> None:
        self.assert_rejected("module = pd\nresult = module.read_csv('.env')")
        self.assert_rejected("modules = [np]\nresult = modules[0].load('.env')")

    def test_rejects_dataframe_io_and_dynamic_evaluation(self) -> None:
        self.assert_rejected("df.to_csv('copy.csv')\nresult = df")
        self.assert_rejected("result = df.query('@__builtins__')")
        self.assert_rejected("result = df.pipe(open, '.env')")

    def test_allows_normal_dataframe_analysis(self) -> None:
        PandasQueryAgent._validate_code_safety(
            "result = df.groupby('region', as_index=False)['sales'].sum().sort_values('sales', ascending=False)"
        )
        PandasQueryAgent._validate_code_safety(
            "result = pd.crosstab(df['region'], df['category'])"
        )
        PandasQueryAgent._validate_code_safety(
            "result = np.where(df['sales'] > df['sales'].mean(), '高', '低')"
        )


if __name__ == "__main__":
    unittest.main()
