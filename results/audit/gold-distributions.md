# VLADBench gold-label audit
Public annotation revision: `1895f22252f9a702fed95334c8e3b60280b4c626`. No images or inference.

Counts cover full source annotations, no historical one-question exclusion. Groups separate answer option sets; yes/no groups split by input selector. Repeated questions share samples and are not independent trials. No pooled categorical baseline across incompatible options.

|Task|Samples|Questions|Yes/no gold (all views)|
|---|---:|---:|---|
|Traffic_Light|129|795|—|
|Pavement_Marking|119|564|—|
|Traffic_Sign|250|701|—|
|Right_Of_Way|103|309|—|
|VRU_Recognition|135|424|—|
|Vehicle_Recognition|98|223|—|
|Vehicle_Status|113|257|—|
|Lane_Recognition|100|780|—|
|Obstruction_Recognition|224|680|{'no': 190, 'yes': 7}|
|Light|100|200|—|
|Weather|124|248|—|
|Sign_Sign_Relation|55|192|—|
|Sign_Lane_Relation|124|1072|—|
|Light_Lane_Relation|111|702|—|
|Lane_Speed_Relation|44|340|—|
|Lane_Change_Relation|108|784|—|
|VRU_Cutin|89|267|{'yes': 94, 'no': 84}|
|Vehicle_Cutin|87|261|{'yes': 172, 'no': 2}|
|VRU_Cross|92|276|{'yes': 176, 'no': 8}|
|Long_Short_Parking|98|320|—|
|Vehicle_Bahavior|80|80|—|
|VRU_Bahavior|99|99|—|
|Key_Obsturction_Detection|154|547|{'yes': 394, 'no': 153}|
|Spatial_Temporal_Reasoning|87|161|{'yes': 10, 'no': 4}|
|Risk_Prediction|103|272|{'yes': 94, 'no': 18}|
|Drive_Efficiency|101|303|—|
|Longitudinal|101|101|—|
|Lateral|109|235|—|
|Trajectory|0|0|—|

## Binary judgment baselines
|Task / input|Questions|Source samples|Majority|Exact-match baseline|
|---|---:|---:|---|---:|
|Obstruction_Recognition / yes_no|197|197|no|96.45%|
|VRU_Cutin / yes_no [image_path]|89|89|yes|52.81%|
|VRU_Cutin / yes_no [image_path_plot]|89|89|yes|52.81%|
|Vehicle_Cutin / yes_no [image_path]|87|87|yes|98.85%|
|Vehicle_Cutin / yes_no [image_path_plot]|87|87|yes|98.85%|
|VRU_Cross / yes_no [image_path]|92|92|yes|95.65%|
|VRU_Cross / yes_no [image_path_plot]|92|92|yes|95.65%|
|Key_Obsturction_Detection / yes_no|547|154|yes|72.03%|
|Spatial_Temporal_Reasoning / yes_no [image_path]|14|13|yes|71.43%|
|Risk_Prediction / yes_no [image_path]|112|103|yes|83.93%|

## Interpretation
The JSON contains per-task, per-answer-space distributions, exact source references and normalization differences. Majority baselines are descriptive label-frequency baselines, not composite scores. They do not by themselves invalidate model rankings.
Trajectory has no scorer mapping, is skipped explicitly in evaluate_vlm.py, and the catalog-derived English annotation URL returns404. No trajectory distribution is claimed.
Grounding uses IoU and model-name-dependent coordinate conversion; relationship IDs are local to images and award partial credit; speed limits award half credit per bound. These are not treated as categorical class frequencies.
The scorer iterates predictions, not all questions: missing predictions can shrink the evaluated denominator. Full-run completeness must be checked separately.
No image-based ground-truth correctness claim is made. Option-set groups are conservative partitions; human semantic review is still required.

## Scorer audit
- evaluate_utils.py:112 general scorer lowercases references but does not trim them; Judge_criterion_QA at354 additionally clean_string trims a limited punctuation set.
- evaluate_utils.py:119 and analogous loops iterate prediction length, so absent predictions can reduce denominators.
- evaluate_vlm.py:54 composite combines distinct metrics: not simply accuracy. Judge metrics include judgment accuracy, description accuracy, and a prompt-substring instruction score.
- evaluate_utils.py:216 relation scoring awards partial credit per matched ID, with no deduplication of predicted IDs; repeated IDs can inflate scores.
- evaluate_utils.py:147 grounding conversion depends on model name and sample dimension; validate coordinate conventions before comparing providers.
- evaluate_utils.py:317 speed bounds score independently; relationship/lane improvement scores compare first and second question halves rather than independent examples.
