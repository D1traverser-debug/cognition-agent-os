from pathlib import Path
import json
import unittest

R = Path(__file__).resolve().parents[1]
S = R / ".agents/skills/engineering-solution-assessment/SKILL.md"

class TestEngineeringMethodPackage(unittest.TestCase):
    def test_skill_and_repo_entrypoint(self):
        agents = (R / "AGENTS.md").read_text(encoding="utf-8")
        body = S.read_text(encoding="utf-8")
        self.assertIn(".agents/skills/engineering-solution-assessment/SKILL.md", agents)
        self.assertTrue(body.startswith("---\n"))
        self.assertIn("name: engineering-solution-assessment", body)
        for name in ("method-selection.md", "failure-classes.md", "learning-and-transfer.md"):
            self.assertTrue((S.parent / "references" / name).is_file())

    def test_method_cards_fit_nonfit(self):
        data = json.loads((R / "knowledge/engineering-methods/method_cards_v1.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["cards"]), 9)
        for c in data["cards"]:
            self.assertTrue(c["primary_source"].startswith("https://"))
            self.assertTrue(c["choose_when"] and c["avoid_when"] and c["independent_probe"])
            self.assertIn("NOT_VALIDATED", c["evidence_status"])

    def test_behavior_cases_not_falsely_claimed(self):
        data = json.loads((R / "evaluation/engineering_method_behavior_cases_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "NOT_EXECUTED")
        self.assertGreaterEqual(len(data["cases"]), 7)
        self.assertEqual(len({c["id"] for c in data["cases"]}), len(data["cases"]))

if __name__ == "__main__":
    unittest.main()
