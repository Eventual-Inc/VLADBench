---
name: evaluate-model
description: Run VLADBench on a named model (an OpenRouter model or an OpenAI-compatible endpoint), score it, and compare it with the published results. Use when asked to benchmark or evaluate a model on VLADBench.
---

# Evaluate a model

1. **Write a protocol file for the model.** Copy one model entry from `results/protocols/full-original.json` into a
   new file, for example `results/protocols/<name>.json`, keeping the top-level fields and changing `name`.
   Pick the entry whose transport matches the model:
   - `video_mp4` (see `gemini38`) if the model accepts MP4 video; `ordered_image_urls` (see `luna56`) if it takes images only.
   - `endpoint`: any OpenAI-compatible chat completions URL, for example `http://localhost:8000/v1` for a vLLM server.
   - `model`: the provider's model string. `credential.variable`: the environment variable that holds its key.
   - `reasoning_effort`: `none` if reasoning can be turned off, otherwise the lowest level the endpoint accepts.
   - Keep `protocol` unchanged: temperature null, original prompts, native-pixel coordinates, 8192 max tokens.
   Validate: `uv run vladbench validate results/protocols/<name>.json`.
2. **Smoke test.** `uv run vladbench run results/protocols/<name>.json --smoke --models <id>`. Report the answers in
   `results/runs/<name>-smoke/<id>/`: all 99 should have `finish_reason: stop` and a non-empty answer, and
   `vladbench score ... --smoke --models <id>` should give every task a score. For OpenRouter,
   sum `usage.cost` and multiply by about 11,193 / 99 × 0.9 for a full-sweep estimate (measured on Gemini 3.8 Flash; smoke tests overestimate).
   Obtain approval for the full run when the estimate exceeds a few dollars.
3. **Full run.** `uv run vladbench run results/protocols/<name>.json --models <id>`. It resumes if stopped.
4. **Score.** `uv run vladbench score results/protocols/<name>.json --models <id>`. Check `dataset_complete` and
   `protocol_complete` in the output.
5. **Compare.** Read `results/scores-<id>.json` and `results/rerun.json` with `uv run python`:
   - TOTAL: `vladbench.aggregate.total(tasks)` where `tasks` maps task name to `{"score", "questions_scored"}`
     (take `questions_scored` from `denominators`).
   - Per-task scores against the published models, and which tasks it wins or loses.
   - If it answers bounding boxes on a 0-1000 grid, its three box-task scores are near zero under the protocol; say so,
     and compare `total(tasks, skip=vladbench.boxes.BOX_TASKS)` as well.
6. **Report** TOTAL, rank among the published models, the biggest task gains and losses, sweep cost, and the caveats
   that apply (box convention, reasoning setting, one run).

To add the model to the published results instead, add it to `results/protocols/full-original.json` and
`results/models.json`, then run `uv run vladbench build`. That changes the public numbers; confirm with a maintainer.
