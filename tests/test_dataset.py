"""Annotation loading: cache, audited copy, download; and sample validation."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vladbench import dataset
from vladbench.dataset import (DEFAULT_REVISION, annotation_bytes, audited_bytes, cached_bytes, download, load_task,
                               task_info, validate_sample)

TASK = "Weather"
SAMPLES = [{"id": "s1", "country": "China", "questions": ["a.png; Day or night?"], "reference": ["day"]}]
DATA = json.dumps(SAMPLES).encode()


def response(data: bytes):
    return BytesIO(data)


class AnnotationBytesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.info = task_info(TASK)

    def test_first_load_downloads_then_serves_from_checksummed_cache(self):
        with patch("vladbench.dataset.urlopen", return_value=response(DATA)) as fetch, patch("vladbench.dataset.audited_bytes", return_value=None):
            self.assertEqual(annotation_bytes(TASK, DEFAULT_REVISION, self.root / "cache"), DATA)
            self.assertEqual(annotation_bytes(TASK, DEFAULT_REVISION, self.root / "cache"), DATA)
        self.assertEqual(fetch.call_count, 1)
        cache, digest = dataset.cache_paths(self.info, DEFAULT_REVISION, self.root / "cache")
        self.assertEqual(digest.read_text().strip(), hashlib.sha256(DATA).hexdigest())
        cache.write_bytes(b"[]")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            cached_bytes(cache, digest, TASK)

    def test_audited_copy_is_used_only_when_its_recorded_hash_matches(self):
        audited = self.root / "results/audit/gold_metadata" / self.info["annotation_path"]
        audited.parent.mkdir(parents=True)
        audited.write_bytes(DATA)
        report = self.root / "results/audit/gold-distributions.json"
        report.write_text(json.dumps({"revision": DEFAULT_REVISION, "tasks": [{"name": TASK, "sha256": hashlib.sha256(DATA).hexdigest()}]}))
        with patch("vladbench.dataset.REPO_ROOT", self.root):
            self.assertEqual(audited_bytes(self.info, TASK, DEFAULT_REVISION), DATA)
            audited.write_bytes(b"[]")
            self.assertIsNone(audited_bytes(self.info, TASK, DEFAULT_REVISION))
            report.unlink()
            self.assertIsNone(audited_bytes(self.info, TASK, DEFAULT_REVISION))

    def test_download_refuses_oversized_and_non_json_bodies(self):
        with patch("vladbench.dataset.urlopen", return_value=response(b"x" * (dataset.ANNOTATION_LIMIT + 1))):
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                download(self.info)
        with patch("vladbench.dataset.urlopen", return_value=response(b"<html>rate limited</html>")), patch("vladbench.dataset.audited_bytes", return_value=None):
            with self.assertRaises(json.JSONDecodeError):
                annotation_bytes(TASK, DEFAULT_REVISION, self.root / "cache")
        self.assertFalse((self.root / "cache").exists(), "an error page must never be cached")

    def test_unavailable_and_unknown_tasks(self):
        with self.assertRaisesRegex(ValueError, "Trajectory"):
            annotation_bytes("Trajectory", DEFAULT_REVISION, self.root)
        with self.assertRaisesRegex(ValueError, "Unknown task"):
            task_info("Nope")

    def test_load_task_validates_every_sample(self):
        with patch("vladbench.dataset.annotation_bytes", return_value=b"{}"):
            with self.assertRaisesRegex(ValueError, "nonempty list"):
                load_task(TASK)
        bad = [dict(SAMPLES[0], country=None)]
        with patch("vladbench.dataset.annotation_bytes", return_value=json.dumps(bad).encode()):
            with self.assertRaisesRegex(ValueError, "missing country"):
                load_task(TASK)


class ValidateSampleTests(unittest.TestCase):
    def check(self, sample, message):
        with self.assertRaisesRegex(ValueError, message):
            validate_sample(sample, TASK, 0)

    def test_structure(self):
        self.check(None, "not an object")
        self.check({"questions": [], "reference": [], "country": "x"}, "aligned")
        self.check({"questions": ["a;b"], "reference": ["x", "y"], "country": "x"}, "aligned")
        self.check({"questions": ["a;b"], "reference": ["x"]}, "missing country")

    def test_question_strings(self):
        base = {"reference": ["x"], "country": "x"}
        self.check(dict(base, questions=["no separator"]), "invalid question/selector")
        self.check(dict(base, questions=[42]), "invalid question/selector")
        self.check(dict(base, questions=[" ; text"]), "empty selector")
        self.check(dict(base, questions=["a.png;   "]), "empty selector")

    def test_sequence_selectors(self):
        base = {"reference": ["x"], "country": "x", "sequence": "clip"}
        self.check(dict(base, questions=["[frames; q"], frames=["f1"]), "invalid sequence selector")
        self.check(dict(base, questions=["[frames]; q"]), "invalid sequence selector")
        self.check(dict(base, questions=["[frames]; q"], frames=[]), "invalid sequence selector")
        self.check(dict(base, questions=["[frames]; q"], frames=["f1"], sequence=""), "missing sequence folder")
        validate_sample(dict(base, questions=["[frames]; q"], frames=["f1"]), TASK, 0)
        validate_sample({"questions": ["a.png; q"], "reference": ["x"], "country": "x"}, TASK, 0)


if __name__ == "__main__":
    unittest.main()
