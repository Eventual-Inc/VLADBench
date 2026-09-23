"""Rebuild the committed outputs and compare byte for byte.

The steps that need only committed files run everywhere, CI included. The record and the answer files also need the
sweep records under results/runs/, which are not in git, so those checks run where the records exist.
"""
import filecmp
import json
from pathlib import Path
import tempfile
import unittest

from vladbench import paths
from vladbench.boxes import variants
from vladbench.record import build_record, load_record
from vladbench.registry import load_registry
from vladbench.site import build_site
from vladbench.sitedata import FILES, site_file, task_inputs, write_js, write_site_data
from vladbench.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
HAVE_RUNS = paths.RUNS.is_dir() and any(paths.RUNS.iterdir())


class CommittedOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load_record()
        cls.tmp = Path(tempfile.mkdtemp())

    def same(self, ours: Path, committed: Path):
        self.assertTrue(filecmp.cmp(ours, committed, shallow=False), f"{ours.name} differs from the committed {committed}")

    def test_site_data(self):
        for path in write_site_data(self.record, task_inputs(), self.tmp):
            with self.subTest(file=path.name):
                self.same(path, site_file([k for k, (name, _) in FILES.items() if name == path.name][0]))

    def test_variants(self):
        path = write_js(self.tmp / FILES["variants"][0], FILES["variants"][1], variants(self.record, load_registry()))
        self.same(path, site_file("variants"))

    def test_site_bundle(self):
        site = build_site(self.tmp / "pages")
        for name in ("index.html", "results.html", "embed.html", "self-test.html", "rerun.json", "web/config.js", *(n for n, _ in FILES.values())):
            with self.subTest(file=name):
                self.assertTrue((site / name).is_file())
        self.assertNotIn("task-review-data.js", (site / "embed.html").read_text())
        self.assertEqual(len(list((site / "answers").glob("*.json"))), 28)

    @unittest.skipUnless(HAVE_RUNS, "sweep records not present")
    def test_record(self):
        record = build_record(load_spec(paths.PROTOCOL), load_registry())
        self.assertEqual(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", paths.RECORD.read_text())

    @unittest.skipUnless(HAVE_RUNS, "sweep records not present")
    def test_answers(self):
        from vladbench.answers import write_answers
        for path in write_answers(self.record, task_inputs(), self.tmp / "answers"):
            with self.subTest(task=path.stem):
                self.same(path, paths.ANSWERS / path.name)


if __name__ == "__main__":
    unittest.main()
