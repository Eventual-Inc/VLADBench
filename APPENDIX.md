# Appendix: VLADBench Vehicle Cut-in details

This appendix contains the detailed results, attribution analysis, related work, and complete checklist for [the forthcoming article](https://eventual.ai/blog/open-loop-vlm-evals-scenario-mining).

## Complete scores and scoring

**The Score isn't a proxy for Cut-in detection**. The official composite score from the paper is calculated as 70% yes/no judgment, 10% reason, 20% "did you copy an option from the question."

The complete run tables are in the [official leaderboard](LEADERBOARD.md) and [reworded-prompt leaderboard](LEADERBOARD-reword.md).

## Observed sweep spend

Actual recorded spend for the sweep was $53.824, or about $54. The chart labels identify billing coverage where known.

![Observed Modal and OpenRouter spend across the model sweep](plots/article/02-observed-sweep-spend.png)

## Exact prompt-rewrite results

| Model               | Judgment, official | Judgment, reworded | False positives |
| ------------------- | ------------------ | ------------------ | --------------- |
| Qwen3.6-35B-A3B-FP8 | 31.6%              | 71.8%              | 0 → 1           |
| Qwen3.6-35B-A3B     | 29.3%              | 65.5%              | —               |
| GPT-6 Astra         | 25.9%              | 52.3%              | 0 → 0           |
| Gemini 3.8 Flash    | 15.5%              | 18.4%              | 0 → 0           |

## Reasoning and single-run caveat

Turning reasoning on did not help the models that were already ahead. Qwen FP8 dropped from 31.6% judgment to 20.7%. The extra thinking made it more literal, not more visual. That is the first failure mode, and we found it before we changed a word of the prompt.

Relative ranking across a large sweep is operationally more useful than a single heroic run on one model. We ran each configuration once. I am not going to pretend that is a confidence interval. It is enough to choose which configurations deserve replication, not to make a production claim.

## Then we tried to grade "why"

The third question asserts the cut-in and asks for a reason from a short list. The most common gold reason, 44 of 86 scored clips, is `commuting efficiency`. It is not defined in the paper, the supplement, or the JSON. It is a motive: they moved into ego's path to get ahead. You cannot see that in a last frame. You can see a Honda on a dashed line. The models say `lane change`. Gold uses `lane change` twice.

![Distribution of VLADBench gold reason labels, dominated by commuting efficiency](plots/article/07-reason-label-distribution.png)

This is the point where I got angry at the benchmark as a grading instrument, not just as a prompt. Cut-in is hard to see. Explaining it in a taxonomy that mixes geometry (`merge onto main road`) with unobservable intent is harder. We did not "correct" those golds to `lane change`. That would be fitting labels to the predictions we already had. What we can say is: once the English was honest, GPT-6's reason accuracy fell (25.6% → 18.6%) and the number of clips it got fully right — yes, yes, and the canned reason — fell from 13 to 7. With the broken prompt it had been matching the benchmark's favorite phrase. Ask the real question and the reason head falls apart.

Designing the eval is the job. If the classes are not in the pixels, you are not measuring perception.

## What the authors did next

The VLADBench paper does not publish a postmortem on this task. Three months later, an overlapping author group (including Yue Li and Meng Tian) put out [Drive-R1](https://arxiv.org/abs/2506.18234) (AAAI 2026). The question there is no longer "did the VLM answer the VQA." The opening result is a planner that does as well or better without camera data. The model was using history and ego state, not the image. They evaluate on nuScenes and DriveLM, not on VLADBench.

That later paper is not a VLADBench postmortem, but it demonstrates the broader risk: open-loop visual question answering can look like understanding while the model is not looking. Separately, [Bench2Drive-VL](https://arxiv.org/abs/2604.01259) (April 2026), from a different research group, contrasts closed-loop evaluation with the previous generation of open-loop VQA. VLADBench's own limitations section is narrower. It asks for multi-view and better domain training. It does not ask whether the questions are the task.

I went to VLADBench to pick a model. The later papers investigate different evaluation problems; they do not prove why the authors changed direction. My narrower finding is that this VQA task was not a stable measurement of cut-in detection.

## A list of ways not to do this

I failed so you don't have to. From the most naive to least, try to avoid these assumptions when working with your fleet logs:

1. **Do not treat scoring as a model pick without reading the question.** If the prompt does not reflect the scenario, you are ranking overfit results, not perception. The scenario is a spec worth spending time on.
2. **Do not assume the prompt wording transfers across models.** Four words, forty points on Qwen, almost nothing on Gemini. Write the question you mean. Test it on every vendor.
3. **Do not turn on chain-of-thought and assume vision improved.** On this task, thinking almost always made the leader more literal and worsened scores.
4. **Do not trust a high pass rate on a yes-set.** 86 of 87 clips here are positives. Fleet video is the opposite. You have not measured the false-alarm cost.
5. **Do not treat a bounding box as a free accuracy boost.** Answers change. Sometimes they get worse. You now depend on a detector you may not have.
6. **Do not put motives in the taxonomy.** `commuting efficiency` is not a visual class. `lane change` is. Grade what is in the frame.
7. **Do not skip the sweep.** One model on one prompt is just one datapoint. Sweeping twenty configurations told us which configurations not to prioritize on this harness.
8. **Do not use open-loop VQA as a proxy for scenario mining.** This task did not establish whether the model actually used the image, and separate closed-loop work measures behavior much further from a yes/no over a handful of JPEGs.
