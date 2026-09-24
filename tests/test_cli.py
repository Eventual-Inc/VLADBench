"""The three commands dispatch to the right function with the parsed options."""
import io
import json
import os
from pathlib import Path
import tempfile
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

    def test_score_smoke_prints_each_task(self):
        result = {"model_id": "luna56", "dataset_complete": False, "protocol_complete": False, "truncated_answers": 0,
                  "request_success": {"completed": 3, "total": 3}, "source": str(ROOT / "results/runs/full-original-smoke/luna56"),
                  "tasks": {"Weather": {"score": 50.0}, "Light": {"score": None, "exclusions": [{"reason": "no judgment question"}]}}}
        out = io.StringIO()
        with patch("vladbench.scoring.score_model", return_value=result) as score, redirect_stdout(out):
            main(["score", SPEC, "--smoke", "--models", "luna56"])
        self.assertTrue(score.call_args.kwargs["smoke"])
        self.assertIn("Weather", out.getvalue())
        self.assertIn("unscorable: no judgment question", out.getvalue())
        self.assertIn("results/runs/full-original-smoke/luna56/scores.json", out.getvalue())

    def test_unknown_model_is_a_one_line_error(self):
        with patch("vladbench.scoring.score_model"), self.assertRaisesRegex(SystemExit, "vladbench score: unknown model ids"):
            main(["score", SPEC, "--models", "nope"])

    def test_debug_shows_the_original_error(self):
        with patch("vladbench.scoring.score_model"), patch.dict(os.environ, {"VLADBENCH_DEBUG": "1"}), self.assertRaises(ValueError):
            main(["score", SPEC, "--models", "nope"])

    def test_build_reports_written_and_skipped_steps(self):
        from vladbench.build import BuildReport
        report = BuildReport(models=["a"], written={"site": [Path("x")]}, skipped=["record", "answers", "export"])
        out = io.StringIO()
        with patch("vladbench.build.build", return_value=report) as build, redirect_stdout(out):
            main(["build"])
        self.assertIsNone(build.call_args.kwargs["steps"])
        self.assertIn("site       1 file\n", out.getvalue())
        self.assertIn("skipped    record, answers, export", out.getvalue())


class PublishTests(unittest.TestCase):
    def setUp(self):
        from vladbench.export import TABLES
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name)
        self.files = [f"{t}.parquet" for t in TABLES] + ["README.md"]
        self.patches = [patch("vladbench.paths.DATASET", self.dataset), patch("dotenv.load_dotenv")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def fill(self):
        for name in self.files:
            (self.dataset / name).write_text("")

    def test_missing_tables_stop_before_upload(self):
        with self.assertRaisesRegex(SystemExit, "run vladbench build first"):
            main(["publish"])

    def test_dry_run_names_the_target(self):
        self.fill()
        out = io.StringIO()
        with redirect_stdout(out):
            main(["publish", "--dry-run", "--repo", "someone/data"])
        self.assertIn("Would publish", out.getvalue())
        self.assertIn("someone/data", out.getvalue())

    def test_a_missing_token_stops_before_upload(self):
        self.fill()
        with patch.dict(os.environ, {}, clear=True), patch("vladbench.publish.publish_dataset") as upload:
            with self.assertRaisesRegex(SystemExit, "HF_TOKEN"):
                main(["publish"])
        upload.assert_not_called()

    def test_upload_uses_the_token(self):
        self.fill()
        out = io.StringIO()
        with patch.dict(os.environ, {"HF_TOKEN": "t"}), patch("vladbench.publish.publish_dataset", return_value="done") as upload, redirect_stdout(out):
            main(["publish"])
        self.assertEqual(upload.call_args.kwargs["token"], "t")
        self.assertEqual(out.getvalue().strip(), "done")


if __name__ == "__main__":
    unittest.main()
