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
            self.assertFalse(report["parse_errors"])

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
