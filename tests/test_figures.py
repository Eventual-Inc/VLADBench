"""The Cost vs Score figures: label placement helpers, and both PNGs rendered from the committed record."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from vladbench.figures import _choose_anchor, _inside, _overlaps, _uncross, cost_points, render_figures
from vladbench.record import load_record
from vladbench.registry import load_registry


class PlacementTests(unittest.TestCase):
    def test_boxes_overlap_only_when_they_share_area(self):
        self.assertTrue(_overlaps((0, 0, 10, 10), (5, 5, 10, 10)))
        self.assertFalse(_overlaps((0, 0, 10, 10), (10, 0, 10, 10)))

    def test_inside_needs_the_whole_box_within_bounds(self):
        self.assertTrue(_inside((1, 1, 5, 5), (0, 0, 10, 10)))
        self.assertFalse(_inside((8, 1, 5, 5), (0, 0, 10, 10)))

    def test_first_free_candidate_is_taken(self):
        dx, dy, ha, _ = _choose_anchor(50, 50, 20, 10, 1.0, [], (0, 0, 100, 100))
        self.assertEqual((dx, dy, ha), (10, 0, "left"))

    def test_a_blocked_candidate_moves_to_the_next(self):
        blocker = (55, 40, 30, 20)  # covers the right-hand label
        dx, _, ha, box = _choose_anchor(50, 50, 20, 10, 1.0, [blocker], (0, 0, 100, 100))
        self.assertEqual((dx, ha), (-10, "right"))
        self.assertFalse(_overlaps(box, blocker))

    def test_no_room_falls_back_to_the_right(self):
        dx, dy, ha, _ = _choose_anchor(50, 50, 20, 10, 1.0, [(0, 0, 100, 100)], (0, 0, 100, 100))
        self.assertEqual((dx, dy, ha), (10, 0, "left"))

    def test_crossed_leaders_swap_labels(self):
        a = {"leader": True, "dot": (0, 0), "centre": (10, 10)}
        b = {"leader": True, "dot": (10, 0), "centre": (0, 10)}
        _uncross([a, b])
        self.assertEqual((a["centre"], b["centre"]), ((0, 10), (10, 10)))

    def test_labels_without_leaders_stay(self):
        a = {"leader": False, "dot": (0, 0), "centre": (10, 10)}
        b = {"leader": True, "dot": (10, 0), "centre": (0, 10)}
        _uncross([a, b])
        self.assertEqual(a["centre"], (10, 10))


class CostPointsTests(unittest.TestCase):
    def test_points_skip_models_not_featured_or_without_cost(self):
        record = load_record()
        record["models"][0]["featured"] = False
        record["models"][1]["usage"] = {}
        ids = {p["id"] for p in cost_points(record, load_registry())}
        self.assertNotIn(record["models"][0]["id"], ids)
        self.assertNotIn(record["models"][1]["id"], ids)
        self.assertIn(record["models"][2]["id"], ids)


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "uv sync --group scripts for matplotlib")
class RenderTests(unittest.TestCase):
    def test_both_figures_render_at_their_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = render_figures(load_record(), load_registry(), Path(tmp))
            sizes = [struct.unpack(">II", p.read_bytes()[16:24]) for p in paths]
        self.assertEqual(sizes, [(2000, 1125), (1920, 1080)])


if __name__ == "__main__":
    unittest.main()
