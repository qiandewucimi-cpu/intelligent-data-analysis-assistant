import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from analyzer.__main__ import main
from analyzer.agent import PandasQueryAgent


class CLIPrivacyTests(unittest.TestCase):
    def run_cli(self, extra):
        frame = pd.DataFrame({"customer": ["SYNTHETIC_PRIVATE_NAME"], "sales": [25]})
        received = {}

        class RecordingModel:
            def __init__(self, config):
                pass

            def generate_pandas_code(self, **kwargs):
                received["profile"] = kwargs["dataframe_profile"]
                return "result = df"

            def explain_query_result(self, **kwargs):
                received["preview"] = kwargs["result_preview"]
                return "fixture"

        # Keep the real CLI -> profile -> agent -> model call chain;
        # stub only external configuration, file loading and process execution.
        with patch("analyzer.__main__._load_config", return_value=SimpleNamespace(provider="test", model_name="fixture")), \
             patch("analyzer.__main__._read_input", return_value=frame), \
             patch("analyzer.__main__.load_dotenv"), \
             patch("analyzer.__main__.LLMService", RecordingModel), \
             patch("analyzer.agent.run_in_sandbox", return_value=SimpleNamespace(ok=True, result_frame=frame)), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["fixture.csv", "-q", "总额", "--no-clean", *extra]), 0)
        return received

    def test_default_hides_samples_categories_and_result_text_from_model(self):
        received = self.run_cli([])
        self.assertEqual(received["profile"]["sample_rows"], [])
        self.assertNotIn("SYNTHETIC_PRIVATE_NAME", str(received))
        self.assertIn("***", received["preview"])

    def test_explicit_opt_out_allows_samples(self):
        received = self.run_cli(["--no-desensitize"])
        self.assertIn("SYNTHETIC_PRIVATE_NAME", str(received["profile"]))
        self.assertIn("SYNTHETIC_PRIVATE_NAME", received["preview"])
