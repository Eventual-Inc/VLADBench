# Reproduction

```sh
pip install -e .            # numpy, pillow, python-dotenv; ffmpeg must be on PATH for video models
cp .env.example .env        # OPENROUTER_API_KEY; HF_TOKEN to publish

vladbench validate results/protocols/full-original.json
vladbench run results/protocols/full-original.json --smoke --models inkling qwen38max   # first question of every task (billable)
vladbench run results/protocols/full-original.json --models inkling                     # everything unanswered (billable)
vladbench score results/protocols/full-original.json --models inkling                   # writes results/scores-inkling.json
python3 scripts/build_review_results.py                                                  # rebuilds results/ and the companion assets
PYTHONPATH=src python3 scripts/export_parquet.py                                 # writes results/dataset/*.parquet for publishing
PYTHONPATH=src python3 scripts/publish_hf.py [--dry-run]                         # dataset card + Space build; uploads with HF_TOKEN
python3 -m http.server                                                           # open /results.html, /task-review.html or /self-test.html
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
