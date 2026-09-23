"""Per-question marks re-aggregate to the released scorer's components for every model and task."""
from pathlib import Path
import unittest

from vladbench.per_question import components_from_marks, question_mark, sample_marks
from vladbench.scoring import GROUNDING, JUDGE

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs/full-original"


class MarkTests(unittest.TestCase):
    def test_choice_question_accepts_exact_or_unambiguous_containing_answer(self):
        q = "x.png;Pick one from ['Red', 'Green', 'Yellow']."
        self.assertEqual(question_mark("Geneal_criterion_QA", q, "Red", "Red")["accuracy"], 1)
        self.assertEqual(question_mark("Geneal_criterion_QA", q, "Red", "The light is red.")["accuracy"], 1)
        self.assertEqual(question_mark("Geneal_criterion_QA", q, "Red", "Red or Green")["accuracy"], 0)
        self.assertEqual(question_mark("Geneal_criterion_QA", q, "Red", "Red")["instruction"], 1)

    def test_box_question_scores_iou_and_needs_exactly_one_box(self):
        q = "x.png;Where is the car located in the image?"
        mark = question_mark(GROUNDING, q, [10, 10, 110, 110], "[10, 10, 110, 110]")
        self.assertEqual((mark["accuracy"], mark["instruction"]), (1, 1))
        self.assertAlmostEqual(mark["other"], 1.0)
        two = question_mark(GROUNDING, q, [10, 10, 110, 110], "[10, 10, 110, 110] and [0,0,5,5]")
        self.assertEqual((two["accuracy"], two["instruction"]), (0, 0))

    def test_judgment_versus_description_kind(self):
        self.assertEqual(question_mark(JUDGE, "x;Is it risky? ['Yes', 'No']", "Yes", "Yes")["kind"], "judgment")
        self.assertEqual(question_mark(JUDGE, "x;Describe it.", "Braking", "Braking")["kind"], "description")

    def test_paired_flag_sits_on_the_second_question(self):
        sample = {"questions": ["a;Speed? [min, max]", "b;Speed? [min, max]"], "reference": ["[30, 60]", "[30, 60]"]}
        marks = sample_marks("RoadSpeed_criterion_QA", sample, ["[30, 60]", "[30, 60]"])
        self.assertIsNone(marks[0]["pair"])
        self.assertEqual(marks[1]["pair"], 1)
        self.assertEqual(components_from_marks("RoadSpeed_criterion_QA", marks)[2], 1.0)


@unittest.skipUnless(RUNS.is_dir() and (ROOT / "results/rerun.json").exists(), "sweep records not present")
class ReproductionTests(unittest.TestCase):
    def test_marks_reproduce_released_components_for_every_model_and_task(self):
        from vladbench.answers import check_marks, mark_task, recorded_answers
        from vladbench.record import load_record
        from vladbench.requests import questions
        from vladbench.scoring import load_scorer
        models = load_record()["models"]
        scorers = load_scorer()[0].func_mapping
        for task in ("Traffic_Light", "VRU_Recognition", "Sign_Lane_Relation", "Lane_Speed_Relation", "Lane_Change_Relation", "Vehicle_Cutin"):
            requests = questions(task)
            family = scorers[task].__name__
            for model in models:
                marks = mark_task(family, recorded_answers(model["id"], task), requests)
                if marks is None:
                    continue
                with self.subTest(task=task, model=model["id"]):
                    check_marks(task, family, model, marks)   # raises MarksMismatch on a difference


if __name__ == "__main__":
    unittest.main()
