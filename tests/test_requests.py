"""Request construction: one builder, model differences only where declared."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vladbench.dataset import DEFAULT_REVISION, list_tasks, remote_url, validate_sample
from vladbench.requests import build, digest, questions
from vladbench.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_spec(ROOT / "results/protocols/full-original.json")
MODELS = {m["id"]: m for m in SPEC["models"]}
SAMPLE: dict = {"id": "s1", "country": "China", "questions": ["first.png; Keep ; punctuation."], "reference": ["yes"]}
SEQUENCE = {"id": "s2", "country": "China", "sequence": "scene", "image_path": ["frame_9.png", "frame_2.png", "frame_5.png"],
            "questions": ["[image_path]; What happened?"], "reference": ["yes"]}


class FakeMedia:
    def lossless(self, urls):
        return Path("/tmp/fake.mp4"), b"video", {"encoded_sha256": digest(urls), "frames": [{"url": u} for u in urls]}


def question(sample, task="Vehicle_Cutin", smoke=False):
    with patch("vladbench.requests.load_task", return_value=[sample]):
        return questions(task, smoke=smoke)[0]


class QuestionTests(unittest.TestCase):
    def test_prompt_keeps_exact_text_and_pinned_urls(self):
        q = question(SAMPLE)
        self.assertEqual(q["prompt"], "The image is from China.  Keep ; punctuation.")
        self.assertIn("/" + DEFAULT_REVISION + "/", q["image_urls"][0])
        self.assertFalse(q["sequence"])

    def test_sequence_order_is_annotation_order_not_filename_order(self):
        q = question(SEQUENCE)
        self.assertEqual([u.rsplit("/", 1)[-1] for u in q["image_urls"]], SEQUENCE["image_path"])
        self.assertTrue(q["prompt"].startswith("The sequence is from China."))

    def test_identity_is_stable_and_changes_with_the_question(self):
        self.assertEqual(question(SAMPLE)["id"], question(SAMPLE)["id"])
        changed = copy.deepcopy(SAMPLE)
        changed["questions"][0] += " Changed."
        self.assertNotEqual(question(SAMPLE)["id"], question(changed)["id"])

    def test_dataset_guards(self):
        with self.assertRaisesRegex(ValueError, "aligned"):
            validate_sample(dict(SAMPLE, reference=[]), "Vehicle_Cutin", 0)
        with self.assertRaises(ValueError):
            remote_url("task/../secret", DEFAULT_REVISION)
        tasks = list_tasks()
        self.assertEqual(sum(t["available"] for t in tasks), 28)
        self.assertFalse(next(t for t in tasks if t["name"] == "Trajectory")["available"])


class BuildTests(unittest.TestCase):
    def test_question_text_and_budget_are_identical_across_models(self):
        q = question(SEQUENCE)
        payloads = {mid: build(SPEC, m, q)[0] for mid, m in MODELS.items()}
        self.assertEqual({p["messages"][0]["content"][-1]["text"] for p in payloads.values()}, {q["prompt"]})
        self.assertEqual({p["max_tokens"] for p in payloads.values()}, {SPEC["protocol"]["max_tokens"]})
        self.assertTrue(all("temperature" not in p for p in payloads.values()))

    def test_declared_transport_and_reasoning_shape(self):
        q = question(SEQUENCE)
        qwen, gemini, inkling = (build(SPEC, MODELS[m], q)[0] for m in ("qwen36or", "gemini38", "luna56"))
        self.assertEqual(qwen["messages"][0]["content"][0]["type"], "video_url")
        self.assertEqual(qwen["provider"], {"ignore": ["Alibaba"]}, "video requests for the open Qwen weights avoid the route that rejects short clips")
        self.assertEqual(qwen["reasoning"], {"enabled": False})
        self.assertEqual(gemini["messages"][0]["content"][0]["processing"], "static")
        self.assertEqual(gemini["reasoning"], {"effort": "low"})
        self.assertNotIn("reasoning_effort", gemini)
        gemma = build(SPEC, MODELS["gemma431"], q)[0]
        self.assertEqual(gemma["reasoning"], {"enabled": False})
        self.assertEqual([p["type"] for p in inkling["messages"][0]["content"]], ["image_url"] * 3 + ["text"])
        self.assertEqual(inkling["reasoning"], {"enabled": False})

    def test_still_images_never_become_video(self):
        q = question(SAMPLE)
        for m in MODELS.values():
            payload, _, receipt = build(SPEC, m, q, FakeMedia())
            self.assertEqual([p["type"] for p in payload["messages"][0]["content"]], ["image_url", "text"])
            self.assertIsNone(receipt)
            self.assertNotIn("mm_processor_kwargs", payload)

    def test_protocol_hash_is_media_independent_and_single_frames_go_as_is(self):
        q = question(SEQUENCE)
        placeholder, h1, _ = build(SPEC, MODELS["qwen36or"], q)
        real, h2, receipt = build(SPEC, MODELS["qwen36or"], q, FakeMedia())
        self.assertEqual(h1, h2)
        self.assertTrue(real["messages"][0]["content"][0]["video_url"]["url"].startswith("data:video/mp4;base64,"))
        assert receipt is not None
        self.assertEqual(receipt["encoded_sha256"], digest(q["image_urls"]))
        single = question(dict(SEQUENCE, image_path=["only.png"]))
        for model in ("qwen36or", "gemini38"):
            self.assertEqual(build(SPEC, MODELS[model], single)[0]["messages"][0]["content"][0]["video_url"]["encoded_frames"], 1)

    def test_smoke_is_the_first_question_only(self):
        with patch("vladbench.requests.load_task", return_value=[SAMPLE, SEQUENCE]):
            self.assertEqual(len(questions("Vehicle_Cutin", smoke=True)), 1)
            self.assertEqual(len(questions("Vehicle_Cutin")), 2)


class SpecTests(unittest.TestCase):
    def test_live_spec_loads(self):
        self.assertEqual(SPEC["protocol"]["max_tokens"], 8192)
        self.assertEqual(len(SPEC["models"]), 15)

    def test_undeclared_deviations_are_rejected(self):
        cases = {
            "image model with video options": lambda s: next(m for m in s["models"] if m["id"] == "luna56")["video_options"].update({"payload": {"x": 1}}),
            "video model without frame policy": lambda s: s["models"][0].update({"single_frame_policy": "not_applicable"}),
            "temperature set": lambda s: s["protocol"].update({"temperature": 0.0}),
            "unknown transport": lambda s: s["models"][0].update({"input_transport": "frames"}),
            "extra model key": lambda s: s["models"][0].update({"note": "x"}),
        }
        base = json.loads((ROOT / "results/protocols/full-original.json").read_text())
        for name, mutate in cases.items():
            changed = copy.deepcopy(base)
            mutate(changed)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
                json.dump(changed, handle)
            try:
                with self.subTest(name), self.assertRaises(ValueError):
                    load_spec(Path(handle.name))
            finally:
                Path(handle.name).unlink()


if __name__ == "__main__":
    unittest.main()


class OversizeFallbackTests(unittest.TestCase):
    class Media:
        def __init__(self):
            self.compressed_calls = 0

        def lossless(self, urls):
            return Path("/tmp/big.mp4"), b"x" * 64, {"encoded_sha256": "big", "frames": [{"url": u} for u in urls]}

        def compressed(self, urls, path, receipt):
            self.compressed_calls += 1
            return Path("/tmp/small.mp4"), b"y", dict(receipt, encoded_sha256="small", provider_size_fallback=True)

    def test_declared_fallback_is_used_and_receipted_when_the_body_is_too_large(self):
        q = question(SEQUENCE)
        media = self.Media()
        with patch("vladbench.requests.PROVIDER_BODY_LIMIT", 100):
            payload, h, receipt = build(SPEC, MODELS["gemini38"], q, media)
        self.assertEqual(media.compressed_calls, 1)
        assert receipt is not None
        self.assertTrue(receipt["provider_size_fallback"])
        self.assertEqual(receipt["encoded_sha256"], "small")
        self.assertEqual(h, build(SPEC, MODELS["gemini38"], q)[1], "the protocol hash ignores which encoding was sent")

    def test_no_fallback_declared_means_a_hard_error(self):
        with patch("vladbench.requests.PROVIDER_BODY_LIMIT", 100), self.assertRaisesRegex(ValueError, "no fallback"):
            build(SPEC, dict(MODELS["gemini38"], oversize_fallback="none"), question(SEQUENCE), self.Media())
