# Protocol

This document describes how the re-evaluation was run and how problems were handled as they came up. The settings
live in `results/protocols/full-original.json`, and the file's hash identifies the condition.

## How the benchmark was run

- **Dataset.** `depth2world/VLADBench` at revision `1895f222…`: 28 tasks, 11,193 questions per model. Trajectory has
  no released references or scorer, so it is left out. The paper's final scores leave it out too.
- **Prompts.** Each question's original text, after the country sentence that the released sample uses. There is no
  system prompt and there are no examples.
- **Images.** A single-image question sends the pinned dataset URL with `detail: auto`. Images are not resized.
- **Frame sequences.** Each model receives sequences in one of two ways: as an MP4 built from the annotated frames in
  order at 1 FPS, encoded losslessly (crf 0), or as the frames in order as separate images. The table at the end
  shows which.
- **Reasoning.** Off where the provider allows it, and low otherwise.
- **Generation.** Temperature is left unset. `max_tokens` is 8192, as a guard against runaway output. A run counts as
  complete only if no answer reached it.
- **Serving.** Every model was called through OpenRouter, and each model ran once. Differences under about two points
  may be run-to-run noise.
- **Scoring.** The paper's released scorer (`evaluate_utils.py` at commit `b0dde78`), kept under `original/` with one
  syntax fix. Bounding boxes are scored in pixels.

## Quirks and how they were handled

- **Retries.** A request that fails with a transient error is tried up to four times, waiting 1, 2, and 4 seconds
  after rate limits and timeouts, and 10, 20, and 40 seconds after server errors and failed image fetches. An answer
  that comes back empty, is cut off by the guard, or is a single character repeated is asked again, up to four times.
  If no attempt produces an answer, the question is scored as unanswered.
- **Large requests.** OpenRouter rejects request bodies over 20 MB. Videos over the limit were re-encoded with H.264
  at crf 18, which is lossy, and the answer record flags them. This affected 242 Gemini 3.8 Flash requests.
- **Single-frame sequences.** 256 of the 2,684 sequence questions have one annotated frame. Video models receive them
  as a one-frame MP4.
- **Qwen 3.8 Max.** Alibaba's endpoint rejects video with fewer than four frames, which would have affected 876
  sequence questions. Qwen 3.8 Max receives every sequence as separate images instead.
- **Reasoning that cannot be turned off.** Gemini 3.8 Flash, Qwen 3.8 Max, Muse Spark 1.3, MiniMax M3, Claude Opus
  5.5, and GPT-6 Astra run with reasoning low. GPT-6 Astra also accepts `minimal`, which was not used. MiniMax M3
  produces reasoning tokens even when asked not to.
- **Hosts that change per request.** OpenRouter sends MiniMax M3 and Gemma 4 31B to third-party hosts that vary from
  request to request (Parasail, Venice, and Friendli were seen), and the open-weight Qwen models to Darkbloom and
  Parasail. The open-weight Qwen models exclude the Alibaba route, which rejects clips under four frames. The dataset
  records the host that served each answer.
- **Pinned model IDs.** The OpenAI models are called by exact ID, such as `openai/gpt-5.6-luna`, rather than moving
  aliases such as `~openai/gpt-luna-latest`.
- **Gemini 3.8 Flash's first run.** It first ran with a 512-token cap, which cut off 56 answers. Those 56 were asked
  again under the 8192 guard on 2026-09-15, and the other answers were kept. The score file counts the kept answers
  as `carried_from_superseded_condition`. The earlier settings file is archived at
  `scripts/archive/full-original-512.json`.
- **Earlier Qwen runs.** Qwen 3.6 35B A3B and Qwen 3.8 27B first ran on self-hosted Modal endpoints under the same
  512-token cap. OpenRouter runs replaced them, and the old score files are in `results/archive/`.
- **Gemini 2.5 Flash Lite.** It first ran with reasoning low and was re-run with reasoning off. The earlier answers
  are archived.
- **Box units.** The prompt gives the image size in pixels but does not say what units a box should use. Models that
  answer on a 0-1000 grid score near zero on the three box tasks. The site and `vladbench.boxes` also report those
  models with boxes read on their own grid.
- **What providers do.** What a provider does with a request after it arrives (decoding, frame sampling, resizing) is
  not visible to us.

## Tracing an answer to its request

Each answer records the SHA-256 of the request that produced it, with video bytes replaced by the frame URLs they were
built from. The scorer rebuilds each request and refuses an answer whose hash does not match. The kept Gemini 3.8
Flash answers match the archived settings file instead. Media receipts under `results/runs/media/` record the frame
hashes, the video hash, the frame count, and any re-encoding.

## Per-model settings

| Model | Frame sequences | Reasoning | Host |
|---|---|---|---|
| Gemini 3.8 Flash | MP4 | low | provider-managed |
| Gemini 2.5 Flash Lite | MP4 | off | provider-managed |
| Gemma 4 31B | MP4 | off | third-party, varies |
| GPT-5.6 Luna | images | off | OpenAI |
| GPT-5.6 Sol | images | off | OpenAI |
| GPT-6 Luna | images | off | OpenAI |
| GPT-6 Sol | images | off | OpenAI |
| GPT-6 Astra | images | low | OpenAI |
| Claude Opus 5.5 | images | low | Anthropic |
| Qwen 3.8 Max | images | low | Alibaba |
| Qwen 3.8 27B | MP4 | off | third-party, varies; not Alibaba |
| Qwen 3.6 35B A3B | MP4 | off | third-party, varies; not Alibaba |
| Muse Spark 1.3 | MP4 | low | provider-managed |
| MiniMax M3 | MP4 | low | third-party, varies |
| Reka Edge | MP4 | off | provider-managed, not pinned |

Every model is called through OpenRouter. MP4 models send video with `processing: static`.
