"""The three commands dispatch to the right function with the parsed options."""
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from vladbench.cli import main

ROOT = Path(__file__).resolve().parents[1]
SPEC = str(ROOT / "results/protocols/full-original.json")


class CliTests(unittest.TestCase):
    def test_validate_prints_identity_and_protocol(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["validate", SPEC]), 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["name"], "full-original")
        self.assertEqual(printed["protocol"]["max_tokens"], 8192)
        self.assertIn("luna56", printed["models"])

    def test_run_passes_models_and_smoke(self):
        with patch("vladbench.run.run") as run:
            main(["run", SPEC, "--smoke", "--models", "luna56", "muse13"])
        spec, models = run.call_args.args
        self.assertEqual((spec["name"], models, run.call_args.kwargs), ("full-original", ["luna56", "muse13"], {"smoke": True}))

    def test_score_runs_selected_models_and_reports_completeness(self):
        result = {"model_id": "luna56", "dataset_complete": False, "protocol_complete": False, "truncated_answers": 0,
                  "request_success": {"completed": 1, "total": 2}}
        out = io.StringIO()
        with patch("vladbench.scoring.score_model", return_value=result) as score, redirect_stdout(out):
            main(["score", SPEC, "--models", "luna56"])
        self.assertEqual(score.call_count, 1)
        self.assertEqual(score.call_args.args[1]["id"], "luna56")
        self.assertEqual(json.loads(out.getvalue())["request_success"], {"completed": 1, "total": 2})

    def test_unknown_model_is_an_error(self):
        with patch("vladbench.scoring.score_model"), self.assertRaisesRegex(ValueError, "unknown model ids"):
            main(["score", SPEC, "--models", "nope"])


if __name__ == "__main__":
    unittest.main()
