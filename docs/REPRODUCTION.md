# Reproduction

```sh
uv sync --group scripts     # ffmpeg must be on PATH for video models
cp .env.example .env        # OPENROUTER_API_KEY; HF_TOKEN to publish

uv run vladbench validate results/protocols/full-original.json
uv run vladbench run results/protocols/full-original.json --smoke --models gemini38 qwen38max  # a few whole samples per task (billable)
uv run vladbench run results/protocols/full-original.json --models gemini38                    # everything unanswered (billable)
uv run vladbench score results/protocols/full-original.json --models gemini38                  # writes results/scores-gemini38.json
uv run vladbench build                  # record, site data, answers, variants, parquet, figures, card, Pages site; stops on a partial run
uv run vladbench publish [--dry-run]    # uploads results/dataset/ with HF_TOKEN
python3 -m http.server                  # open /results.html or /self-test.html

A new model needs a protocol entry in results/protocols/full-original.json and a registry entry in results/models.json
(label, lab, parameters, size rank, featured, box convention, colour).
```

## What happens

`vladbench.run` loops over models, tasks, and questions. For each question it
builds the request from the specification (`vladbench.requests.build`), sends it
(`post`), and appends one line to `results/runs/<condition>/<model>/<task>.jsonl` with the
answer, finish reason, usage, raw response, and a hash of the request. Running
again asks only the unanswered questions. One retry on 429, 5xx, or timeout;
anything else, including an empty answer, raises and stops the process.

`vladbench score` rebuilds every request from the specification, refuses to
score an answer whose hash does not match, and runs the released scorer once per
task over complete samples. It writes `results/scores-<model>.json`, including
truncation and lossy-fallback counts.

Sequence questions for `video_mp4` models are encoded once into
`results/runs/media/<hash>.mp4` with a receipt beside it, and reused by every model.

Provider-side image fetching, decoding, and resizing are not observed. See
[PROTOCOL.md](PROTOCOL.md) for the protocol, per-model declarations, and claims.
