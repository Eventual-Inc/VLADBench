"""The loop: send unanswered questions, record answers, resume, raise on failure."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from vladbench import run as run_module
from vladbench.run import credential, read_jsonl, run
from vladbench.scoring import score_model
from vladbench.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = {"id": "s1", "country": "China", "questions": ["a.png; Is it day? Answer yes or no.", "b.png; Is it night? Answer yes or no."],
          "reference": ["yes", "no"]}


class FakeServer(ThreadingHTTPServer):
    """Records every request and replies from a script of (status, body) pairs."""
    payloads: list[dict]
    script: list[tuple[int, dict | None]]


class Provider(BaseHTTPRequestHandler):
    server: FakeServer

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.payloads.append(payload)
        status, body = self.server.script.pop(0) if self.server.script else (200, None)
        if body is None:
            body = {"choices": [{"message": {"content": "yes"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: A002 - the base class names it format
        pass


class RunTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer(("127.0.0.1", 0), Provider)
        self.server.payloads, self.server.script = [], []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        spec = load_spec(ROOT / "results/protocols/full-original.json")
        model = dict(next(m for m in spec["models"] if m["id"] == "luna56"), endpoint=f"http://127.0.0.1:{self.server.server_port}/v1")
        self.spec: dict = dict(spec, name="test", models=[model])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runs = Path(self.tmp.name)
        self.patches = [patch("vladbench.run.tasks", return_value=["Weather"]), patch("vladbench.requests.load_task", return_value=[SAMPLE]),
                        patch.dict(run_module.os.environ, {"OPENROUTER_API_KEY": "k"})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def records(self):
        return read_jsonl(self.runs / "test" / "luna56" / "Weather.jsonl")

    def test_answers_are_recorded_and_resume_skips_them(self):
        run(self.spec, runs_dir=self.runs)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(len(self.server.payloads), 2)
        self.assertEqual(self.server.payloads[0]["reasoning"], {"enabled": False})
        run(self.spec, runs_dir=self.runs)
        self.assertEqual(len(self.server.payloads), 2)
        meta = json.loads((self.runs / "test" / "luna56" / "meta.json").read_text())
        self.assertEqual(meta["specification_sha256"], self.spec["sha256"])

    def test_transient_error_is_retried_then_raised(self):
        with patch("vladbench.run.time.sleep") as sleep:
            self.server.script = [(429, {"error": "slow down"})]
            run(self.spec, runs_dir=self.runs)
            self.assertEqual(len(self.records()), 2)
            sleep.assert_called_once_with(1)
            attempts = self.spec["protocol"]["max_attempts"]
            self.server.script = [(500, {"error": "still down"})] * (2 * attempts)  # two questions, every attempt fails
            spec = dict(self.spec, name="test2")
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                run(spec, runs_dir=self.runs)
            self.assertIn(10, {c.args[0] for c in sleep.call_args_list}, "outages back off in tens of seconds")

    def test_provider_image_fetch_failures_are_retried(self):
        body = {"error": {"message": "Provider returned error", "metadata": {"raw": "media_url_not_fetchable: failed to download media"}}}
        self.server.script = [(400, body)]
        with patch("vladbench.run.time.sleep") as sleep:
            run(self.spec, runs_dir=self.runs)
        sleep.assert_called_once_with(10)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(max(r["attempt"] for r in self.records()), 2)

    def test_empty_answer_with_stop_is_redrawn(self):
        self.server.script = [(200, {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]})]
        run(self.spec, runs_dir=self.runs)
        self.assertEqual([r["answer"] for r in self.records()].count(""), 0)
        self.assertEqual(max(r["attempt"] for r in self.records()), 2)

    def test_guard_hit_with_no_text_is_redrawn_then_recorded_as_unanswered(self):
        cut = (200, {"choices": [{"message": {"content": ""}, "finish_reason": "length"}], "usage": {"completion_tokens": 8192}})
        self.server.script = [cut]  # one runaway, then normal answers
        run(self.spec, runs_dir=self.runs)
        records = self.records()
        self.assertEqual([r["answer"] for r in records].count(""), 0)
        self.assertEqual(max(r["attempt"] for r in records), 2)
        attempts = self.spec["protocol"]["max_attempts"]
        self.server.script = [cut] * (2 * attempts)  # every draw runs away
        spec = dict(self.spec, name="test2")
        run(spec, runs_dir=self.runs)
        unanswered = [r for r in read_jsonl(self.runs / "test2" / "luna56" / "Weather.jsonl") if r["answer"] == ""]
        self.assertEqual(len(unanswered), 2)
        self.assertTrue(all(r["finish_reason"] == "length" for r in unanswered))

    def test_degenerate_repeated_character_answer_is_redrawn(self):
        junk = (200, {"choices": [{"message": {"content": "!" * 300}, "finish_reason": "length"}], "usage": {"completion_tokens": 8192}})
        self.server.script = [junk]
        run(self.spec, runs_dir=self.runs)
        self.assertTrue(all(r["answer"] == "yes" for r in self.records()))
        self.assertEqual(max(r["attempt"] for r in self.records()), 2)

    def test_crash_truncated_journal_line_is_skipped(self):
        path = self.runs / "x.jsonl"
        path.write_text('{"id": "a"}\n{"id": "b"')
        self.assertEqual([r["id"] for r in read_jsonl(path)], ["a"])
        self.assertEqual(read_jsonl(self.runs / "missing.jsonl"), [])

    def test_credentials_come_from_the_environment_by_declared_name(self):
        env_model = {"id": "m", "credential": {"type": "environment", "variable": "SOME_KEY"}}
        with patch.dict(run_module.os.environ, {"SOME_KEY": "abc"}, clear=True):
            self.assertEqual(credential(env_model), "abc")
        with patch.dict(run_module.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SOME_KEY"):
                credential(env_model)

    def test_timeout_is_retried_then_raised(self):
        with patch("vladbench.run.post", side_effect=TimeoutError("slow")) as post, patch("vladbench.run.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "TimeoutError: slow"):
                run(self.spec, runs_dir=self.runs)
        self.assertLessEqual(post.call_count, 2 * self.spec["protocol"]["max_attempts"])  # two questions in flight

    def test_smoke_asks_only_the_first_question_into_a_separate_condition(self):
        run(self.spec, smoke=True, runs_dir=self.runs)
        self.assertEqual(len(self.server.payloads), 1)
        self.assertTrue((self.runs / "test-smoke" / "luna56" / "Weather.jsonl").exists())

    def test_score_verifies_request_hashes_before_scoring(self):
        run(self.spec, runs_dir=self.runs)
        with patch("vladbench.scoring.tasks", return_value=["Weather"]):
            result = score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results")
        self.assertEqual(result["request_success"], {"completed": 2, "total": 2})
        self.assertTrue((self.runs / "results" / "scores-luna56.json").exists())
        path = self.runs / "test" / "luna56" / "Weather.jsonl"
        tampered = [dict(r, protocol_sha256="0" * 64) for r in read_jsonl(path)]
        path.write_text("".join(json.dumps(r) + "\n" for r in tampered))
        with patch("vladbench.scoring.tasks", return_value=["Weather"]), self.assertRaisesRegex(ValueError, "do not match"):
            score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results")

    def test_score_keeps_a_score_file_with_more_answers(self):
        run(self.spec, runs_dir=self.runs)
        with patch("vladbench.scoring.tasks", return_value=["Weather"]):
            score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results")
            saved = (self.runs / "results" / "scores-luna56.json").read_text()
            (self.runs / "test" / "luna56" / "Weather.jsonl").unlink()
            with self.assertRaisesRegex(ValueError, "not overwriting"):
                score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results")
            self.assertEqual((self.runs / "results" / "scores-luna56.json").read_text(), saved)
            forced = score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results", force=True)
        self.assertEqual(forced["request_success"]["completed"], 0)


    def test_carried_answers_count_only_when_their_cap_did_not_bind(self):
        run(self.spec, runs_dir=self.runs)
        path = self.runs / "test" / "luna56" / "Weather.jsonl"
        records = read_jsonl(path)
        old = json.loads(json.dumps(self.spec))
        old["name"], old["protocol"]["max_tokens"] = "old-512", 512
        from vladbench.requests import build
        question = {q["id"]: q for q in __import__("vladbench.requests", fromlist=["questions"]).questions("Weather")}
        carried = [dict(r, protocol_sha256=build(old, old["models"][0], question[r["id"]])[1], condition="old-512") for r in records]
        carried[1]["finish_reason"] = "length"  # the cap bound this one; it must not be accepted
        path.write_text("".join(json.dumps(r) + "\n" for r in carried))
        with patch("vladbench.scoring.tasks", return_value=["Weather"]):
            with self.assertRaisesRegex(ValueError, "do not match"):
                score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results")
            carried[1]["finish_reason"] = "stop"
            path.write_text("".join(json.dumps(r) + "\n" for r in carried))
            self.assertEqual(score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results", superseded=[old])["carried_from_superseded_condition"], 2)
            path.write_text("".join(json.dumps(r) + "\n" for r in carried))
            with self.assertRaisesRegex(ValueError, "do not match"):
                score_model(self.spec, self.spec["models"][0], runs_dir=self.runs, results_dir=self.runs / "results")


if __name__ == "__main__":
    unittest.main()
