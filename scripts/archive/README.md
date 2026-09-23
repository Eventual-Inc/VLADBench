# Archived launchers (provenance only)

These scripts produced the recorded runs under `results/runs/` before the single
specification-driven launcher existed. They are kept so that a reader can see
exactly how each earlier group was orchestrated. **Do not run them for new
results.** Each one hard-codes a model, endpoint, or protocol choice, and their
protocol choices drifted from one another:

| Script | Runs it produced | Protocol it hard-coded |
|---|---|---|
| `run_managed_full.py` | `results/runs/managed-qwen-fp8-full-original` (abandoned) | MP4 video, reasoning `none`, 512 tokens, sequential |
| `run_managed_three.py` | `results/runs/managed-three-models-full-original`, `results/runs/managed-qwen36-full-resumed`, `results/runs/managed-qwen38-full-resumed` | MP4 video with `mm_processor_kwargs.do_sample_frames=false`, single-frame sequences padded to two frames, reasoning `none`, 512 tokens |
| `run_gemini_full.py` | `results/runs/gemini-full-original-low`, `results/runs/openrouter-muse-qwenmax-full-original-low` | MP4 video with `processing: static`, OpenRouter `reasoning: {effort: low}`, H.264 fallback above 20 MB, 512 tokens for Gemini and Qwen Max but 2048 for Muse |
| `run_modal_full.py` | `results/runs/modal-deepseek-inkling-full-original-lowest` | Ordered `image_url` parts, `reasoning_effort` low/minimal, 512 tokens in the recorded children although the file now says 2048 |
| `run_video_smoke.py`, `run_gemini_video_smoke.py`, `run_managed_video_smoke.py` | 28-question smoke runs | One first question per task |
| `score_managed_suite.py`, `summarize_*.py`, `supervise_gemini_full.py` | `scores.json`, `usage-summary.json` in the groups above | Scoring and bookkeeping for the groups above |
| `openai_video_request.py` | none | Manual single request |
| `audit_gold_distributions.py` | `results/audit/gold-distributions.json`, `.md` (committed) | None: it reads the pinned annotations only. Archived 2026-09-22 until the audit post needs new numbers; to be rewritten as `vladbench audit` |
| `full-original-512.json` | the condition the three complete models (qwen36, qwen38, gemini38) were verified against | Identical to `protocols/full-original.json` except for a 512-token completion cap that bound reasoning models |

The recorded requests themselves are the ground truth. On 2026-09-14 every request these
scripts sent for the three complete models was regenerated from `full-original-512.json`
and matched; the resulting score files are the ones in `results/`. The runs under `results/runs/`
use the layout these scripts wrote and are not read by the current code.
