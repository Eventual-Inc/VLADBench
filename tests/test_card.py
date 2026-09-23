"""The dataset card's checks catch the template mistakes the review found."""
import json
from pathlib import Path
import unittest

from vladbench.card import check_card, render_card, table_errors

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "results/rerun.json").read_text())


class CardTests(unittest.TestCase):
    def render(self, template: str) -> str:
        return render_card(RECORD, template, repo="Eventual-Inc/VLADBench-reeval", protocol_sha256="0" * 64)

    def test_published_template_passes(self):
        check_card(self.render((ROOT / "docs/hf-dataset-card.md").read_text()), RECORD)

    def test_unfilled_placeholder_fails(self):
        with self.assertRaisesRegex(ValueError, "unfilled @NOT_A_FIELD@"):
            check_card(self.render((ROOT / "docs/hf-dataset-card.md").read_text() + "\n@NOT_A_FIELD@\n"), RECORD)

    def test_placeholder_inside_a_table_row_is_caught(self):
        # The bug the review found: @MODEL_ROWS@ inside a row shifts the first row and leaves a stray one.
        card = self.render("| A | B |\n| - | - |\n| @MODEL_ROWS@ |   |\n")
        self.assertTrue(table_errors(card))

    def test_a_model_the_card_never_names_fails(self):
        with self.assertRaisesRegex(ValueError, "is not named"):
            check_card("# empty", RECORD)


if __name__ == "__main__":
    unittest.main()
