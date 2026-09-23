---
name: check-a-task
description: Inspect one VLADBench task's questions, references, and every model's answers to judge whether its score can be trusted and why models fail it. Use when asked whether a task or benchmark score is reliable, why models miss a task, or to audit references.
---

# Check a task

Task names are the dataset's keys, including its misspellings (`Vehicle_Bahavior`, `Key_Obsturction_Detection`).
The list is in `results/rerun.json` under `task_order`.

`answers/<Task>.json` holds every question with its prompt, reference (`gold`), frame paths (relative to `base`),
and `answers[model_id] = [text, accuracy, instruction, other, pair]`.

Look for, with `uv run python`:

1. **Questions no model gets right** (`accuracy` 0 for every model). Open a few frames (`base` + image path) and read
   the reference. On Weather and Light these were reference problems, for example a dusk clip with a bright sky
   labelled nighttime.
2. **Lopsided references.** Count reference values. Vehicle cut-in has 172 of 174 yes/no references as "yes", so
   answering yes to everything scores about 99% on that component.
3. **References that are not among the offered options** (Traffic Light has several).
4. **Format failures**: `instruction` 0 means the answer was not in the requested format.
5. **Box tasks** (`VRU_Recognition`, `Vehicle_Recognition`, `Obstruction_Recognition`): scored in pixels; models
   that answer on a 0-1000 grid score near zero. `results/models.json` has each model's `box_convention`.
6. **Spread**: the task's mean and standard deviation across models, from `results/rerun.json`.

Report what fraction of the score each problem could explain, with question ids, and point to the site's Explore and
Caveats tabs (https://eventual-inc.github.io/VLADBench/) for the same data. Known issues are listed in
`docs/hf-dataset-card.md` and `docs/reviews/`.
