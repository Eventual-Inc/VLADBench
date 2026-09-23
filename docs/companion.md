# Reading the results companion

How to read each panel of https://eventual-inc.github.io/VLADBench/. Each panel's description links to its section here.

TOTAL is the mean of the 28 task scores, each weighted by its number of questions. A task score combines accuracy,
instruction following, and a task-specific component with the paper's per-task weights; it is not plain accuracy.
Trajectory, the 29th task, has no released references or scorer and is not scored. Every model ran once, so
differences under about two points may be run-to-run noise.

## Task wheel

The rings show the five domains, then the ten task groups, then the 28 scored tasks under the paper's abbreviations.
Each bar is one model's score on one task, from 0 at the inner edge to 100 at the outer edge. Click a bar to open the
task in Explore. In radar mode, each axis is one task group and each polygon is one model; a model's value on an axis
is the question-weighted mean of that group's tasks, and the outer ring is 100.

## Table 10 layout

Each cell is one model's score on one task, in the layout of the paper's Table 10: its task abbreviations and order,
a MEAN row after each task group, and TOTAL last. Columns are grouped by lab, smallest model first. The best score in
each row is underlined. MEAN and TOTAL weight each task by its number of questions. The paper does not state its
weighting; this rule reproduces 241 of the paper's 250 group averages within 0.1.

## Paper Table 10

The paper's Table 10 as published in 2025. Its models, inference stack, and image handling differ from this
re-evaluation, so the two tables are read side by side, not merged. Row labels are as printed.

## Leaderboard

Score is TOTAL. Sweep cost is the provider-billed cost of all 11,193 answers. Input cost per frame, output cost per
query, and the hourly estimate use the settings of the video cost calculator on the Cost tab (1280x720, 1 FPS,
8-frame clips by default). The latency box spans the 25th to 75th percentile of per-request time, the tick is the
median, and the dot is the 95th percentile. Reka Edge (a 7B edge model) is kept in the data and every other tab but
left out of the leaderboard and the cost plot as an outlier.

## Tasks by audit result and saturation

Each chip is one task and shows its field mean and standard deviation across the models shown. Rows show whether the
audit of the released annotations found a problem with the task's references or grading. Columns show whether the
task is near saturation: field mean at or above 75, or every model within a few points of the others. Click a task
to open it in Explore.

## With and without bounding boxes

Three tasks ask for a bounding box. The prompt gives the image size in pixels but does not state the box units.
OpenAI and Anthropic models answer in pixels; Qwen, Muse, Gemma, MiniMax, and Reka answer on a 0 to 1000 grid, and
Gemini on that grid with y before x. The protocol scores every box as pixels. Each row is one model: the filled dot
is TOTAL as scored, the open dot is TOTAL with boxes read on the model's own grid, and the columns also give TOTAL
without the three box tasks.

## Suspect reference answers

Accuracy grouped by reference answer for one task. Each row is one reference answer and each cell is one model's
accuracy on the questions with that reference. References that no model matched are marked. Tasks flagged by the
audit are listed first.

## One prompt change on Vehicle cut-in

Judgment accuracy under the official question ("the intention to cross the road") and a reworded one ("intend to cut
in") on 260 shared questions. These runs come from an earlier runner with some settings that differ from the protocol,
so they are not comparable to the leaderboard.

## Score distribution per task

Grey dots are the models in the paper's Table 10 (2025); coloured dots are the 2026 runs, without Reka Edge. The bar
is the median, the diamond the mean, and the band one standard deviation either side. The columns show the change in
mean, median, and standard deviation from 2025 to 2026, or one year's values; click a column to sort. The 2025 cohort
includes driving-specialised and domain-trained models, and the evaluation conditions differ, so year-to-year
differences are descriptive.

## What if a reference answer is wrong

Pick a task and tick questions to exclude them; every model's task score and TOTAL are recomputed from the
per-question marks. Paired tasks exclude a question's partner with it. Exclusions stay in the browser and do not
change the published scores.

## Cost vs Score

Each dot is one model: the x axis is the cost of the full sweep (log scale by default), the y axis is TOTAL. The
dashed staircase joins the models that no cheaper model beats. The dotted curves are constant TOTAL per dollar. The
box-scoring control switches every number on the tab between the three readings described above.

## Cost-Performance Frontier

Each row is a price range. The model in the row has the highest TOTAL of any model that costs that much or less.

## Frontier by Box Scoring

Each row is one model, ordered by sweep cost. Each column is TOTAL under one reading of the three box tasks: pixels as
scored, each model's own grid, or the box tasks left out. A marked cell means the model is on the frontier under that
reading.

## Serving Efficiency

Each row is one featured model. Median and 95th-percentile answer time are per request, measured by the harness
through OpenRouter, so they include routing and network time. Models that take ordered images and models that take
video receive different payloads, so answer times are comparable within a transport more than across. Cost per video
hour follows the video cost calculator's settings. Rows are sorted by the 95th percentile, so the models whose slowest
answers are fastest come first.

## Metered Cost of Video Question Answering

Cost of one hour of video question answering at the chosen frame size, frame rate, and clip length, with one question
per clip and no overlap. Tokens per frame come from each provider's tokeniser rule, fitted to the billed tokens of the
sweeps (`src/vladbench/metering.py`). Prices are the per-token rates the sweeps were billed. Output tokens per query
are measured and include reasoning. Open-weight models were served by several hosts, so their prices are blends.

## Explore

Each cell shows one model's answer to one question. The tint shows the credit the answer earned under the paper's
scoring code; a dotted underline means the answer was not in the requested format. Click a row to show its clip.
