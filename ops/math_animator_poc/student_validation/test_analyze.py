import csv
import tempfile
import unittest
from pathlib import Path

from analyze import analyze, load_rows


class AnalyzeStudentValidationTest(unittest.TestCase):
    def test_complete_positive_crossover_passes(self) -> None:
        rows = []
        for participant_index in range(8):
            for concept in ("secant_tangent", "riemann_sum", "taylor_approximation"):
                rows.extend(
                    [
                        {
                            "participant_id": f"p{participant_index}",
                            "concept": concept,
                            "condition": "static",
                            "order": 1,
                            "correct": 0 if participant_index < 2 else 1,
                            "duration_seconds": 100,
                            "helpfulness": None,
                            "adverse_effect": False,
                            "severe_adverse": False,
                        },
                        {
                            "participant_id": f"p{participant_index}",
                            "concept": concept,
                            "condition": "animation",
                            "order": 2,
                            "correct": 1,
                            "duration_seconds": 80,
                            "helpfulness": 4,
                            "adverse_effect": False,
                            "severe_adverse": False,
                        },
                    ]
                )

        result = analyze(rows)

        self.assertTrue(result["gate_passed"])
        self.assertEqual(result["complete_participants"], 8)

    def test_loader_rejects_duplicate_cell(self) -> None:
        fieldnames = [
            "participant_id",
            "concept",
            "condition",
            "order",
            "correct",
            "duration_seconds",
            "helpfulness",
            "adverse_effect",
            "severe_adverse",
            "notes",
        ]
        duplicate = {
            "participant_id": "p1",
            "concept": "secant_tangent",
            "condition": "animation",
            "order": "1",
            "correct": "1",
            "duration_seconds": "10",
            "helpfulness": "5",
            "adverse_effect": "false",
            "severe_adverse": "false",
            "notes": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "responses.csv"
            with path.open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(duplicate)
                writer.writerow(duplicate)

            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_rows(path)


if __name__ == "__main__":
    unittest.main()
