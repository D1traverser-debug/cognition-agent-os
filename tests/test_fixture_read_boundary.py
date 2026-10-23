"""Adversarial checks for the shared fixture-read trust boundary.

These test the actual returned bytes, not the implementation's self-reported
path validation. The race is deterministic and uses only temporary files.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os.source import MAX_SOURCE_BYTES, SourceUnavailable, safe_fixture


class FixtureReadBoundaryTests(unittest.TestCase):
    def test_symlink_swapped_after_validation_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            approved = parent / "approved"
            approved.mkdir()
            inside = approved / "source.txt"
            outside = parent / "external.txt"
            inside.write_bytes(b"approved-data")
            outside.write_bytes(b"outside-data")
            original_is_file = Path.is_file
            swapped = False

            def swap_after_file_check(path):
                nonlocal swapped
                result = original_is_file(path)
                if path == inside and result and not swapped:
                    try:
                        path.unlink()
                        path.symlink_to(outside)
                    except (OSError, NotImplementedError) as exc:
                        self.skipTest(f"symlink creation unavailable: {exc}")
                    swapped = True
                return result

            with patch.object(Path, "is_file", swap_after_file_check):
                with self.assertRaises((ValueError, SourceUnavailable, OSError)):
                    safe_fixture(approved, "source.txt")
            self.assertTrue(swapped, "race injection must actually execute")

    def test_stable_internal_symlink_retains_existing_read_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "allowed"
            root.mkdir()
            real = root / "original.txt"
            real.write_bytes(b"same-in-root")
            alias = root / "alias.txt"
            try:
                alias.symlink_to(real)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            self.assertEqual(safe_fixture(root, "alias.txt"), b"same-in-root")

    def test_static_external_symlink_and_oversized_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = parent / "allowed"
            root.mkdir()
            outside = parent / "external.txt"
            outside.write_bytes(b"outside")
            alias = root / "alias.txt"
            try:
                alias.symlink_to(outside)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            with self.assertRaises(ValueError):
                safe_fixture(root, "alias.txt")
            large = root / "large.bin"
            large.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
            with self.assertRaises(SourceUnavailable):
                safe_fixture(root, "large.bin")


if __name__ == "__main__":
    unittest.main()
