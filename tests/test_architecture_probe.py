"""Bounded tests for static inventory; not evidence of complete call-graph coverage."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "architecture_probe.py"
spec = importlib.util.spec_from_file_location("architecture_probe", MODULE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ArchitectureProbeTests(unittest.TestCase):
    def test_import_edges_and_dynamic_disclosure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pkg = root / "src" / "cognition_agent_os"
            pkg.mkdir(parents=True)
            (pkg / "a.py").write_text(
                "from . import b\nfrom .b import thing\n__import__('hidden')\n", encoding="utf-8")
            (pkg / "b.py").write_text("def thing(): pass\n", encoding="utf-8")
            report = probe.inspect(root)
            a = next(x for x in report["modules"] if x["name"] == "a")
            self.assertEqual(a["imports"], ["b"])
            self.assertEqual(a["dynamic_import_lines"], [3])
            b = next(m for m in report["modules"] if m["name"] == "b")
            self.assertEqual(b["imported_by"], ["a"])
            self.assertEqual(len(a["source_sha256"]), 64)
            self.assertEqual(a["description_origin"], "UNVERIFIED_SOURCE_DOCSTRING")
            self.assertEqual(probe.focus(report, ["b"])["selected_count"], 2)
            self.assertEqual(probe.focus(report, ["b"], hops=0)["selected_count"], 1)
            self.assertFalse(report["parse_errors"])

    def test_current_repository_is_fully_parsed(self):
        root = Path(__file__).resolve().parents[1]
        report = probe.inspect(root)
        expected = list((root / "src" / "cognition_agent_os").glob("*.py"))
        self.assertEqual(report["file_count"], len(expected))
        self.assertEqual(report["parsed_count"], len(expected))
        self.assertFalse(report["parse_errors"], report["parse_errors"])
        names = {item["name"] for item in report["modules"]}
        self.assertIn("host", names)
        self.assertIn("runner", names)
        self.assertIn("ledger", names)

    def test_source_change_invalidates_locator_and_focus_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pkg = root / "src" / "cognition_agent_os"
            pkg.mkdir(parents=True)
            source = pkg / "alpha.py"
            source.write_text('"""First purpose."""\nfrom . import beta\n',
                              encoding="utf-8")
            (pkg / "beta.py").write_text('"""Second purpose."""\n',
                                         encoding="utf-8")
            before = probe.inspect(root)
            alpha = next(m for m in before["modules"] if m["name"] == "alpha")
            self.assertEqual(alpha["source_description"], "First purpose.")
            self.assertEqual(probe.focus(before, ["beta"])["selected_count"], 2)
            with self.assertRaises(ValueError):
                probe.focus(before, ["not_a_module"])
            with self.assertRaises(ValueError):
                probe.focus(before, ["beta"], hops=3)
            source.write_text(source.read_text(encoding="utf-8").replace(
                "First purpose", "Changed purpose"), encoding="utf-8")
            after = probe.inspect(root)
            newer = next(m for m in after["modules"] if m["name"] == "alpha")
            self.assertNotEqual(alpha["source_sha256"], newer["source_sha256"])
            self.assertEqual(newer["source_description"], "Changed purpose.")

    def test_unparseable_source_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pkg = root / "src" / "cognition_agent_os"
            pkg.mkdir(parents=True)
            (pkg / "broken.py").write_text("def f(\n", encoding="utf-8")
            report = probe.inspect(root)
            self.assertEqual(report["file_count"], 1)
            self.assertEqual(report["parsed_count"], 0)
            self.assertEqual(report["parse_errors"][0]["error"], "SyntaxError")
