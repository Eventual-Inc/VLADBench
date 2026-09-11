# Open-loop VLM evals are a disappointing proxy for scenario mining.

> **TLDR**
>
> After running 20 completed configurations across 12 VLMs on a vehicle cut-in visual-question-answering task, I re-discovered eight expensive assumptions that ruin robotics evals. Qwen 3.6 35B-A3B topped this harness, but prompt wording, bounding boxes, and a 98.9%-positive label set moved the result enough that the benchmark could not establish production cut-in performance.

---

## VLMs can't save your evals.

Every new customer conversation is the same.

A robotics team tries to use a frontier model to find scenarios in fleet video only to be disappointed with the results. Frontier models have improved drastically over the last year, so I decided I'd revisit a benchmark from last year to see just how good today's models have become.

Turns out the model is a distraction and an expensive one at that.

I ended up testing 20 completed configurations across 12 models on VLADBench's Vehicle Cut-in VQA task and discovered that the task prompt was misleading in English, and that the *reason* attribution was being scored against a label I didn't care about. But these were the concrete failures I encountered on VLADBench. What struck me this time was just how ...

On a task that looks trivially easy, prompting a vision language model open-loop over a few frames is brittle and highly sensitive to prompt variations and bounding box annotations. I'll also caveat that

> **Note:**
>
> [Bench2Drive-VL](https://arxiv.org/abs/2604.01259) (April 2026) is a closed-loop benchmark from a separate research group. It is not VLADBench's direct follow-up; I use it in the appendix as a contrast with open-loop VQA.

A bit of background before we dive in...

AV (Autonomous Vehicle) safety teams leverage a combination of techniques to annotate scenes. The naive promise of frontier VLMs is that you can replace human annotations with machine-generated pseudo-labels. We might be able to solve Navier–Stokes, but this harness could not establish that even GPT-6 Astra detects cut-ins accurately enough to train your next policy.

Detecting vehicle cut-ins is an important scenario in self-driving. A lane change begins when another vehicle crosses a lane boundary; it becomes an ego-relevant cut-in when that vehicle enters the gap ahead of the ego vehicle in its lane or planned path, usually reducing headway and potentially requiring an ego response. There is no single ISO definition that everyone cites, but a cut-in is more specific than simply crossing a dashed line.

## The VLADBench Cut-ins Benchmark

[VLADBench](https://arxiv.org/abs/2503.21505) (ICCV 2025) is an autonomous-driving benchmark spanning 29 closed-form driving tasks. The paper emphasizes that most autonomous driving evaluations bucket capability too broadly, which is the motivation for expanding to fine-grained task suites. I chose to focus on the *Vehicle Cut-in* task, which poses 260 questions against 87 dashcam clips.

"Clips" is generous here. We're not actually shoving video. The VLM is provided with a sequence of two to seven still images and is asked to classify whether or not the scene qualifies as a cut-in. Each model is asked twice, once with just the raw frames, and again with a bounding box around the vehicle of interest, with a simple yes or no. A third question asks the VLM to attribute the reasoning label from a predefined list—basically just structured outputs.

![The three VLADBench Vehicle Cut-in questions shown against their gold labels and a representative Qwen prediction](plots/article/01-benchmark-prompt-anatomy.png)

I looked at this task and was like, "Cool, let's see how many models I can run this benchmark on in the next two hours," and swept 20 completed configurations across 12 open and closed models, with and without reasoning.

## The disappointing results.

The initial survey placed Qwen 3.6 35B-A3B at the top of the official composite score and among the fastest completed configurations. A score of 43.5 out of 100 shows there's still plenty of headroom for improvement. Because the endpoint totals cover different numbers of runs and hardware, this experiment does not establish a normalized cost winner.

Observed spend varied across serving paths, hardware, and the number of configurations covered by each entry. These are account-level experiment totals, not normalized model prices, and Modal GPU time may include startup and idle time. The plot shows where spend accumulated while finding the harness failures, not a price comparison.

![Observed Modal and OpenRouter spend across the model sweep](plots/article/02-observed-sweep-spend.png)

Use the result to compare behavior on this harness; do not use it to decide whether cut-in detection is solved.

![Median model request latency versus VLADBench score across completed runs](plots/article/03-latency-vs-score.png)

Now here is how this actually went:

**The prompt was misleading.** While the task is called `Vehicle_Cutin`, the prompt the model actually receives is:

> does the Sedan in the image have the intention to **cross the road**?

Almost all of the clips show a vehicle moving laterally across or toward a dashed lane marking. Crossing that marking is a lane change; it becomes a cut-in when the vehicle enters the gap ahead of ego. In ordinary English, "cross the road" instead suggests traversing a roadway, often at an intersection.

**The goldens were 98.9% positives**, so an always-yes classifier achieves 98.9% judgment accuracy.

**Intent labels are unverifiable** — you can't recover why a driver merged from two to seven frames, so "commuter efficiency" as a gold answer is scoring the model against a guess. And it isn't what a scenario miner needs anyway; they need what happened and where, not motive.

Qwen 3.6 35B-A3B, quantized to FP8, led the completed official run on judgment accuracy. GPT-6 was close on composite score but slower in this run. The plot includes every completed configuration with timing metadata; with one run per configuration, I do not have enough evidence to explain why Qwen 3.8 scored below Qwen 3.6.

## Then we read the prompt

While the task is called `Vehicle_Cutin`, the prompt the model actually receives is:

> does the Sedan in the image have the intention to **cross the road**?

Almost all of the clips show a vehicle moving laterally across or toward a dashed lane marking. Crossing that marking is a lane change; it becomes a cut-in when the vehicle enters the gap ahead of ego. The official English prompt names a different maneuver.

Gold says yes on 172 of 174 judgment questions. A model that reads English and says no is "wrong." The official leaderboard is partly a ranking of who is willing to ignore the sentence.

That does not make the sweep worthless. It makes the absolute numbers too low, and it makes "thinking" look like a penalty. We reworded one phrase for the top of the board — "intend to cut in (enter or cross into the ego vehicle's path)" — and left gold, frames, and scoring alone.

![Judgment accuracy before and after replacing the official crossing-the-road wording with cut-in wording](plots/article/04-prompt-rewrite-comparison.png)

The order of the models we re-ran did not change. Qwen FP8, then Qwen, then GPT-6, then Gemini. If you came to this task to pick a model, that ranking is the thing that survived. The scores did not. Four words moved Qwen by forty points. Gemini barely moved. Specificity is not a style choice. It is a hyperparameter, it does not transfer across vendors, and on a fleet you will not have a folder name to warn you that the prompt is almost the right question.

I am not going to relabel the gold to make anyone look better. The ranking held. The magnitudes did not. Both of those facts matter.

[The exact reworded results are in the appendix.](APPENDIX.md#exact-prompt-rewrite-results)

## The yes-set problem

The reworded Qwen number looks like a pass. 71.8% judgment, 71.1 composite, one false positive. Then you count the labels. 86 of 87 clips are gold-yes. There is one true-negative clip, asked twice. A detector that became more willing to say yes will look improved. We did not get a hard negative set. We cannot tell a careful cut-in detector from a model that stopped saying no.

![VLADBench Vehicle Cut-in label distribution showing 86 positive clips and one negative clip](plots/article/05-label-imbalance.png)

If you mine ambient fleet video, almost every frame is a negative. This benchmark cannot tell you what that costs. Precision on a yes-heavy eval is not precision in the field. The false-positive column staying near zero is comforting until you notice there was almost nothing to be wrong about.

## Draw a box, get a different answer

Each clip is asked twice: raw frames, then the same frames with the target in a red rectangle. Same sentence.

GPT-6 got worse with the box (27.6% → 24.1% on the official wording; 55.2% → 49.4% after the reword). Qwen got better, especially after the reword (65.5% → 78.2%). Gemini moved around. What did not stay still was the decision. Qwen flipped yes/no on 19 of 87 clips when the rectangle appeared; after the reword, 23. GPT-6 flipped on 7, then 19.

![A representative Qwen answer changing from no to yes when a target bounding box is added](plots/article/06-bounding-box-answer-flip.png)

We have seen the drop internally as well: turn localization on, performance moves, usually not in the direction you budgeted for. In a fleet pipeline the box is your detector. You are now paying for a VLM *and* a localizer, and the VLM's answer depends on whether the localizer fired and how tight the box was. Attribution is not a free hint. It is another place the system is brittle.

That is a large part of why throwing a VLM at ambient logs is expensive. You do not just pay per token. You pay for a prompt you cannot validate, a box you may need, and a miss rate you cannot see.

## I am disappointed in both

I am disappointed in most of the vision stack we swept for this job. Below the top five, I would not prioritize another run of these configurations until the eval is fixed. Gemma E2B, Gemma E4B, GPT-5.6 Luna, Qwen 3.8 without thinking, the fine-tune: they are not close on this harness. If you start a replication anywhere, start with Qwen 3.6 35B-A3B. Not because it solved the problem. Because it reached the top with low measured latency, leaving more iteration time for the failure modes below.

I am also disappointed in the top five. They are the ones worth experimenting with, and they are painfully sensitive to the prompt, the box, and the label taxonomy. Qwen is the winner on this harness. It is not a cut-in system.

I am disappointed in the benchmark. The English did not name the task. The classes mixed what you can see with what you cannot. The yes/no split is a cartoon of the fleet. A year-old ICCV paper is allowed to be messy. Using it as a silent production filter is how you ship a miner that looks clean and misses most of the events.

Both can be true. A bad eval does not automatically mean the ranking is bad. Ours held after we fixed the English. It does mean you should not believe the score.

Detecting cut-ins is hard. Writing a perception benchmark for them, especially one that goes through a vision-language model, is harder. The value of the last two days is not a template for evaluating cut-ins open-loop; it is evidence that benchmark design dominated the result. If you build the next experiment, Qwen 3.6 35B-A3B is a reasonable starting point on this harness—not proof of production performance—and the evaluation design deserves at least as much attention as the model.

[The appendix contains the complete scores, exact prompt results, reasoning analysis, reason-label taxonomy, related work, and full checklist.](APPENDIX.md)