"""Box parsing and the own-grid reading, on hand-worked cases."""
from typing import Any
import unittest

from vladbench.boxes import grid_composite, parse_box, to_pixels
from vladbench.scoring import load_scorer

BOX_IOU = load_scorer()[0].box_iou


class ParseTests(unittest.TestCase):
    def test_one_box(self):
        self.assertEqual(parse_box("It is at [100, 200, 300, 400]."), (100, 200, 300, 400))

    def test_zero_or_several_boxes(self):
        self.assertIsNone(parse_box("no box"))
        self.assertIsNone(parse_box("[1, 2, 3, 4] or [5, 6, 7, 8]"))


class ToPixelsTests(unittest.TestCase):
    def test_pixels_unchanged(self):
        self.assertEqual(to_pixels((1, 2, 3, 4), "pixels", 2000, 1000), (1, 2, 3, 4))

    def test_grid_scales_to_the_frame(self):
        self.assertEqual(to_pixels((100, 200, 300, 400), "grid", 2000, 1000), (200, 200, 600, 400))

    def test_grid_yx_swaps_first(self):
        self.assertEqual(to_pixels((200, 100, 400, 300), "grid_yx", 2000, 1000), (200, 200, 600, 400))

    def test_unit_fractions_are_read_on_the_grid(self):
        self.assertEqual(to_pixels((0.1, 0.2, 0.3, 0.4), "grid", 2000, 1000), (200, 200, 600, 400))


class GridCompositeTests(unittest.TestCase):
    """One frame of 2000x1000; the gold box covers x 200-600, y 200-400 in pixels."""

    def composite(self, answers, convention="grid", choice_correct=0, choices=0):
        gold = [200, 200, 600, 400]
        questions = [{"id": f"b{i}", "kind": "box", "gold": gold, "answers": {"m": [a, 0]}} for i, a in enumerate(answers)]
        questions += [{"id": f"c{i}", "kind": "choice", "gold": "A", "answers": {"m": ["A", int(i < choice_correct)]}} for i in range(choices)]
        task: Any = {"weights": {"accuracy": 0.5, "other": 0.3, "instruction_following": 0.2}, "components": {"instruction_following": 1.0}}
        dims = {str(q["id"]): (2000, 1000) for q in questions}
        return grid_composite(task, questions, "m", dims, convention, BOX_IOU)

    def test_exact_hit(self):
        score = self.composite(["[100, 200, 300, 400]"])
        self.assertAlmostEqual(score.mean_iou, 1.0)
        self.assertEqual(score.box_hits, 1.0)
        self.assertAlmostEqual(score.composite, 100.0)

    def test_y_first(self):
        self.assertAlmostEqual(self.composite(["[200, 100, 400, 300]"], "grid_yx").mean_iou, 1.0)

    def test_zero_or_several_boxes_score_nothing(self):
        score = self.composite(["no box here", "[100, 200, 300, 400] or [0, 0, 10, 10]"])
        self.assertEqual((score.mean_iou, score.box_hits), (0.0, 0.0))

    def test_choice_questions_keep_their_released_marks(self):
        self.assertAlmostEqual(self.composite(["[100, 200, 300, 400]"], choice_correct=1, choices=3).accuracy, 2 / 4)


if __name__ == "__main__":
    unittest.main()
