"""results/models.json: every protocol model has a complete, valid entry."""
from pathlib import Path
import unittest

from vladbench.registry import load_registry, model_info, require_models
from vladbench.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
ENTRY = {"label": "M", "lab": "L", "parameters": "7B", "size_rank": 1, "featured": True, "box_convention": "pixels", "color": "#aabbcc"}


class RegistryTests(unittest.TestCase):
    def test_every_protocol_model_is_registered(self):
        require_models(load_registry(), [m["id"] for m in load_spec(ROOT / "results/protocols/full-original.json")["models"]])

    def test_colours_are_unique(self):
        colours = [info.color for info in load_registry().values()]
        self.assertEqual(len(colours), len(set(colours)))

    def test_rejects_bad_entries(self):
        for change in ({"box_convention": "pixel"}, {"color": "red"}, {"extra": 1}, {"featured": False}, {"size_rank": "1"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                model_info("m", {**ENTRY, **change})
        with self.assertRaises(ValueError):
            model_info("m", {k: v for k, v in ENTRY.items() if k != "box_convention"})

    def test_unregistered_model_fails(self):
        with self.assertRaises(ValueError):
            require_models(load_registry(), ["not_a_model"])


if __name__ == "__main__":
    unittest.main()
