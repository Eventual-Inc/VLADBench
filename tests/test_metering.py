"""Tokenisation and billing rules reproduce what the providers billed, offline against the sweeps and live against the API."""
import glob
import json
import os
from pathlib import Path
import unittest

from vladbench.metering import RULES, Prices, TEXT_TOKENS, clip_tokens, frame_tokens, hourly_cost, input_cost, prices_from_openrouter

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs/full-original"
SLUGS = {"luna56": "openai/gpt-5.6-luna", "astra6": "openai/gpt-6-astra", "gemini38": "google/gemini-3.8-flash",
         "gemini25lite": "google/gemini-2.5-flash-lite", "gemma431": "google/gemma-4-31b-it", "qwen36or": "qwen/qwen3.6-35b-a3b",
         "qwen38max": "qwen/qwen3.8-max-0902", "muse13": "meta/muse-spark-1.3", "minimax3": "minimax/minimax-m3", "rekaedge": "rekaai/reka-edge",
         "opus55": "anthropic/claude-opus-5.5", "luna6": "openai/gpt-6-luna", "sol6": "openai/gpt-6-sol"}
# Median billed prompt tokens per frame at 1280x720 over 743 sequence questions, 2026-09-16, minus the question text.
MEASURED_720P = {"luna56": 1102, "astra6": 1102, "luna6": 1102, "sol6": 1102, "gemini38": 63, "gemini25lite": 255, "gemma431": 74, "qwen38max": 945, "opus55": 1199}
# Video paths that are only roughly flat: measured per-frame range at 720p and 1080p, 4 to 6 frame clips.
MEASURED_RANGE = {"muse13": (96, 131), "minimax3": (168, 231), "rekaedge": (54, 60)}
# Qwen's standard tokeniser at 720p, from the hosts that do not subsample (Parasail, CoreWeave, SiliconFlow, Reka, ...):
# 3 frames 1772, 4 frames 1750, 5 frames 2629, 6 frames 2636 billed tokens, so about 880 per pair of frames.
MEASURED_QWEN_CLIPS_720P = {3: 1772, 4: 1750, 5: 2629, 6: 2636}


class RuleTests(unittest.TestCase):
    def test_rules_reproduce_the_billed_tokens_per_frame_at_720p(self):
        for model, measured in MEASURED_720P.items():
            with self.subTest(model):
                self.assertAlmostEqual(frame_tokens(RULES[model], 1280, 720), measured, delta=measured * 0.02)

    def test_roughly_flat_video_paths_sit_inside_their_measured_range(self):
        for model, (low, high) in MEASURED_RANGE.items():
            with self.subTest(model):
                self.assertTrue(low <= frame_tokens(RULES[model], 1280, 720) <= high)

    def test_qwen_pairs_frames_before_tokenising(self):
        for frames, measured in MEASURED_QWEN_CLIPS_720P.items():
            with self.subTest(frames=frames):
                self.assertAlmostEqual(clip_tokens(RULES["qwen36or"], 1280, 720, frames), measured, delta=measured * 0.03)

    def test_openai_patch_rule_scales_with_area_and_matches_1080p(self):
        self.assertAlmostEqual(frame_tokens(RULES["luna56"], 1920, 1080), 2442, delta=30)
        self.assertAlmostEqual(frame_tokens(RULES["luna56"], 2704, 1520), 4908, delta=60)

    def test_google_video_path_ignores_resolution(self):
        self.assertEqual(frame_tokens(RULES["gemini38"], 640, 360), frame_tokens(RULES["gemini38"], 3840, 2160))

    def test_openai_frames_bill_at_the_cache_write_rate(self):
        prices = prices_from_openrouter({"prompt": "0.0000002", "completion": "0.0000012", "input_cache_write": "0.00000025"})
        one_frame = input_cost(RULES["luna56"], prices, 1280, 720, frames=1)
        self.assertAlmostEqual(one_frame, frame_tokens(RULES["luna56"], 1280, 720) * 0.25e-6 + TEXT_TOKENS * 0.2e-6, places=9)

    def test_hourly_cost_is_frames_times_frame_price_plus_queries_times_output(self):
        prices = Prices(prompt=1e-6, completion=10e-6)
        rule = RULES["gemini38"]
        hour = hourly_cost(rule, prices, fps=1, frames_per_query=8, output_tokens_per_query=200)
        self.assertEqual(hour["frames_per_hour"], 3600)
        self.assertEqual(hour["queries_per_hour"], 450)
        expected_in = 450 * (8 * 63 * 1e-6 + TEXT_TOKENS * 1e-6)   # flat rule: 8 frames x 63 tokens
        self.assertAlmostEqual(hour["input_usd"], expected_in, places=9)
        self.assertAlmostEqual(hour["output_usd"], 450 * 200 * 10e-6, places=9)
        self.assertAlmostEqual(hour["total_usd"], hour["input_usd"] + hour["output_usd"], places=9)


@unittest.skipUnless(RUNS.is_dir(), "sweep records not present")
class SweepValidationTests(unittest.TestCase):
    """Offline: the rules plus list prices must reproduce what OpenRouter billed for the actual sweeps."""

    def records(self, model):
        return [json.loads(line) for path in glob.glob(str(RUNS / model / "*.jsonl")) for line in open(path)]

    SINGLE_HOST = {"luna56", "astra6", "gemini38", "gemini25lite", "qwen38max", "muse13", "rekaedge", "opus55"}   # served by their own vendor at list price

    def test_single_host_models_bill_exactly_at_list_price(self):
        from dotenv import load_dotenv
        from vladbench.metering import fetch_prices
        load_dotenv(ROOT / ".env")
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            self.skipTest("OPENROUTER_API_KEY not set")
        prices = fetch_prices(key, list(SLUGS.values()))
        for model in self.SINGLE_HOST:
            with self.subTest(model):
                records = self.records(model)
                if not records:
                    self.skipTest(f"no records for {model}")
                rule, p = RULES[model], prices[SLUGS[model]]
                billed = sum(r["usage"]["cost_details"]["upstream_inference_prompt_cost"] for r in records)
                tokens = sum(r["usage"]["prompt_tokens"] for r in records)
                details = [r["usage"].get("prompt_tokens_details") or {} for r in records]
                written = sum(d.get("cache_write_tokens", 0) for d in details)
                read = sum(d.get("cached_tokens", 0) for d in details)
                modelled = (tokens - written - read) * p.prompt + written * p.input(rule.input_rate) + read * p.input("input_cache_read")
                self.assertAlmostEqual(modelled, billed, delta=billed * 0.01)

    def test_routed_open_weights_bill_above_list_and_effective_prices_reproduce_the_bill(self):
        from vladbench.metering import effective_prices
        for model in ("gemma431", "qwen36or", "minimax3"):
            with self.subTest(model):
                records = self.records(model)
                if not records:
                    self.skipTest(f"no records for {model}")
                p = effective_prices(records)
                billed = sum(r["usage"]["cost_details"]["upstream_inference_cost"] for r in records)
                modelled = sum(r["usage"]["prompt_tokens"] for r in records) * p.prompt + sum(r["usage"]["completion_tokens"] for r in records) * p.completion
                self.assertAlmostEqual(modelled, billed, delta=billed * 0.001)
                self.assertGreater(p.prompt, 0.09e-6, "blended host price sits above the list price floor")


@unittest.skipUnless(os.environ.get("RUN_LIVE_METERING") == "1", "set RUN_LIVE_METERING=1 to spend a few cents against the API")
class LiveMeteringTests(unittest.TestCase):
    """Live: one synthetic 1280x720 frame per model, as an image or as a 1 FPS clip, must bill the rule's tokens within 10%."""

    def test_live_frame_tokens(self):
        import base64
        import io
        from dotenv import load_dotenv
        from PIL import Image
        from vladbench.run import post
        from vladbench.video import encode_mp4
        from vladbench.requests import data_url
        load_dotenv(ROOT / ".env")
        key = os.environ["OPENROUTER_API_KEY"]
        image = Image.radial_gradient("L").resize((1280, 720)).convert("RGB")
        buffer = io.BytesIO(); image.save(buffer, format="JPEG", quality=95)
        jpeg = buffer.getvalue()
        image_part = {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}
        video_part = {"type": "video_url", "video_url": {"url": data_url(encode_mp4([jpeg] * 8, fps=1))}}
        text = "Describe the image in one word."
        for model, slug in SLUGS.items():
            with self.subTest(model):
                video = RULES[model].kind in ("flat", "pair")
                parts = [video_part if video else image_part, {"type": "text", "text": text}]
                payload = {"model": slug, "messages": [{"role": "user", "content": parts}], "max_tokens": 16}
                if RULES[model].kind == "pair":
                    payload["provider"] = {"ignore": ["Alibaba"]}
                response = post("https://openrouter.ai/api/v1", payload, key, 180)
                frames = 8 if video else 1
                expected = clip_tokens(RULES[model], 1280, 720, frames)
                visual = response["usage"]["prompt_tokens"] - 12   # the short live prompt, about a dozen tokens
                # Qwen hosts differ: the standard tokeniser bills the rule, subsampling hosts bill about a third of it.
                tolerance = 0.70 if RULES[model].kind == "pair" else 0.25 if model in MEASURED_RANGE else 0.10
                self.assertAlmostEqual(visual, expected, delta=max(expected * tolerance, 8),
                                       msg=f"host {response.get('provider')} billed {visual} visual tokens")


if __name__ == "__main__":
    unittest.main()
