# Protocol

Every released VLADBench question was sent once, with its original wording, to
each model through that model's own endpoint, and the answers were scored with
the paper's scoring criteria. Models differ in two declared ways: how they receive a
frame sequence, and whether their reasoning can be switched off.

## What the numbers support

- Per-task scores for each model, scored once over complete samples.
- Comparisons between models that share the same sequence transport and
  reasoning availability (Qwen 3.6 vs Qwen 3.8; Gemini vs Muse; Qwen Max vs
  Claude Opus 5.5).
- Ordering claims across all models, stated with the per-model declarations
  attached, for example "Gemini 3.8 Flash scores higher than Qwen 3.8 27B and
  Qwen 3.6 35B A3B on 25 of 28 tasks under these conditions".

## What they do not support

- Treating a gap to the paper's Table 10 as model progress alone. The 2025 and
  2026 numbers come from different model sets, inference stacks, and image
  handling, with unobserved provider preprocessing.
- Attributing a gap to model quality alone. Some models reason at their lowest
  available level, others have reasoning off; Qwen Max, Claude Opus 5.5, and
  the OpenAI models see frames as separate images, the others see a video.
- Reading TOTAL as more than the question-weighted mean of the 28 task
  composites. That weighting reproduces 241 of the paper's 250 group averages
  within 0.1; the paper does not state it.
- Anything about a model whose run is not `protocol_complete` in its score
  file, beyond the footnoted numbers.

## The protocol

Defined by `results/protocols/full-original.json`. One file is one condition.

| | |
|---|---|
| Dataset | `depth2world/VLADBench` at revision `1895f222…`; 28 released tasks, 11,193 questions per model. `Trajectory` has no released annotation or scorer and is excluded, as in the paper. |
| Prompt | The annotation's question text, byte for byte, after the country sentence the released sample uses. No system prompt, no examples. |
| Static questions | One `image_url` to the pinned dataset URL, `detail: auto`, no local resizing. |
| Sequences | Declared per model: a lossless 1 FPS MP4 of the annotation's frames in annotation order, or the frames as ordered `image_url` parts. |
| Reasoning | Each model's lowest enabled setting: off where the provider allows it, otherwise its minimum. |
| Generation | Temperature unset. `max_tokens` 8192 as a runaway guard, not a variable: a model is `protocol_complete` only if no answer hit it. Up to three retries on transient errors: 1, 2, 4 s backoff for rate limits and timeouts, 10, 20, 40 s for provider outages (5xx) and for a provider failing to fetch a dataset image. A response with no visible answer, whether cut off by the guard or returned empty by the host, is redrawn within the same budget; if none of the draws answers, the question is recorded as unanswered. |
| Coordinates | Native pixels in prompts and scoring. |
| Scorer | The released `evaluate_utils.py` at commit `b0dde78`, preserved under `original/` with one disclosed syntax repair. |

## Per-model declarations

| Model | Sequence transport | Reasoning | Single-frame sequences¹ | Oversize² |
|---|---|---|---|---|
| Gemini 3.8 Flash (OpenRouter)³ | MP4, `processing: static` | low, cannot be disabled | one-frame MP4 | H.264 crf18, 242 requests |
| Qwen 3.8 Max (OpenRouter, Alibaba)⁴ | ordered `image_url` parts | low, cannot be disabled | n/a | n/a |
| Muse Spark 1.3 (OpenRouter) | MP4, `processing: static` | low, cannot be disabled | one-frame MP4 | H.264 crf18 if needed |
| MiniMax M3 (OpenRouter)⁵ | MP4, `processing: static` | low, cannot be disabled | one-frame MP4 | H.264 crf18 if needed |
| Gemma 4 31B (OpenRouter)⁵ | MP4, `processing: static` | off | one-frame MP4 | H.264 crf18 if needed |
| GPT-5.6 Luna (OpenRouter, OpenAI) | ordered `image_url` parts | off | n/a | n/a |
| GPT-6 Astra (OpenRouter, OpenAI) | ordered `image_url` parts | low, mandatory; `minimal` also accepted | n/a | n/a |
| GPT-5.6 Sol (OpenRouter, OpenAI) | ordered `image_url` parts | off | n/a | n/a |
| GPT-6 Luna (OpenRouter, OpenAI) | ordered `image_url` parts | off | n/a | n/a |
| GPT-6 Sol (OpenRouter, OpenAI) | ordered `image_url` parts | off | n/a | n/a |
| Claude Opus 5.5 (OpenRouter, Anthropic) | ordered `image_url` parts | low, cannot be disabled | n/a | n/a |
| Gemini 2.5 Flash Lite (OpenRouter) | MP4, `processing: static` | off | one-frame MP4 | H.264 crf18 if needed |
| Reka Edge (OpenRouter) | MP4, `processing: static` | off; non-reasoning model | one-frame MP4 | H.264 crf18 if needed |
| Qwen 3.8 27B (OpenRouter, third-party hosts) | MP4, `processing: static`, Alibaba route excluded | off | one-frame MP4 | H.264 crf18 if needed |
| Qwen 3.6 35B A3B (OpenRouter, third-party hosts) | MP4, `processing: static`, Alibaba route excluded | off | one-frame MP4 | H.264 crf18 if needed |

¹ 256 of the 2,684 sequence questions have a single annotated frame. Video
models receive it as a one-frame MP4.

² OpenRouter rejects bodies above 20 MB. Requests over the limit are re-encoded
with H.264 crf18 and flagged in the answer record and the score file.

³ Gemini 3.8 Flash was first run under an earlier file, identical except for a
512-token cap, archived at `scripts/archive/full-original-512.json`. The cap
bound 56 answers. Answers the cap did not touch are carried into the live
condition unchanged, each keeping its hash under the archived file; the 56 were
re-asked under the live guard on 2026-09-15, and the scorer accepts a carried
answer only when its `finish_reason` shows the cap did not bind. The score file
records `carried_from_superseded_condition`. Qwen 3.6 35B A3B and Qwen 3.8 27B
were also run under that cap on self-hosted Modal endpoints; those sweeps were
replaced by OpenRouter runs under the live protocol, and their score files are
kept in `results/archive/` for reference only.

⁴ Alibaba's endpoint rejects any video with fewer than four frames, which would
have affected 876 of the 2,684 sequence questions, so Qwen Max receives every
sequence as ordered images instead.

⁵ OpenRouter routes these models to third-party hosts that vary per request
(Parasail, Venice, and Friendli were observed), so the serving backend is not
pinned. MiniMax still emits reasoning tokens when asked to disable reasoning;
Gemma does not.

What any provider does after receiving a request (decoding, frame sampling,
resizing) is not observed.

## How an answer is tied to its request

Every recorded answer carries the SHA-256 of the request it was given, computed
with the video bytes replaced by the frame URLs they were built from. Scoring
rebuilds each request from the specification and refuses to score an answer
whose hash differs. Media receipts under `results/runs/media/` record frame
hashes, encoded-video hash, frame count, padding, and any fallback.

The three earlier sweeps were checked the same way against the archived file on
2026-09-14: 3,137 of 3,137 sample runs per model matched, 11,193 answers each,
and regenerating recorded payloads through the current code produced identical
hashes. Runs record the git commit and dirty flag; the request hash is the
provenance.
