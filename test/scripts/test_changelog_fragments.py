import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "changelog_fragments.py"
spec = importlib.util.spec_from_file_location("changelog_fragments", SCRIPT)
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)

BASE = """# Changelog

## [Unreleased]

### Security

* Existing security entry.

### Fixed

* Existing fix.

## [1.0.0] - 2026-01-01

### Security

* Old release entry.
"""


class Fragments(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "changelog.d"
        self.dir.mkdir()
        self.log = Path(tmp.name) / "CHANGELOG.md"
        self.log.write_text(BASE, encoding="utf-8")

    def add(self, name, text):
        (self.dir / name).write_text(text, encoding="utf-8")

    def test_check_accepts_good_names_and_ignores_the_readme(self):
        self.add("README.md", "docs")
        self.add("1903.security.md", "A fix.")
        self.add("captcha-2.fixed.md", "* Another.")
        self.assertEqual(cf.problems(self.dir), [])
        self.assertEqual(cf.main(["check", "--dir", str(self.dir), "--changelog", str(self.log)]), 0)

    def test_check_reports_bad_names_empty_files_and_headings(self):
        self.add("1903.bogus.md", "x")
        self.add("notes.md", "x")
        self.add("5.added.md", "   ")
        self.add("6.fixed.md", "# Heading")
        found = " ".join(cf.problems(self.dir))
        for name in ("1903.bogus.md", "notes.md", "5.added.md: empty", "6.fixed.md: write the entry text"):
            self.assertIn(name, found)
        self.assertEqual(cf.main(["check", "--dir", str(self.dir)]), 1)

    def test_assemble_appends_under_the_right_headings_in_file_name_order_and_removes_the_files(self):
        self.add("2.security.md", "Second security.")
        self.add("1.security.md", "* First security.")
        self.add("3.fixed.md", "A fix.")
        self.assertEqual(cf.assemble(self.dir, self.log), 3)
        text = self.log.read_text(encoding="utf-8")
        unreleased = text.split("## [1.0.0]")[0]
        self.assertLess(unreleased.index("Existing security entry."), unreleased.index("First security."))
        self.assertLess(unreleased.index("First security."), unreleased.index("Second security."))
        self.assertLess(unreleased.index("Second security."), unreleased.index("### Fixed"))
        self.assertLess(unreleased.index("Existing fix."), unreleased.index("A fix."))
        self.assertIn("* Old release entry.", text.split("## [1.0.0]")[1])
        self.assertNotIn("First security", text.split("## [1.0.0]")[1])
        self.assertEqual(list(self.dir.glob("*.md")), [])

    def test_a_missing_heading_is_created_inside_unreleased(self):
        self.add("7.added.md", "New thing.")
        cf.assemble(self.dir, self.log)
        text = self.log.read_text(encoding="utf-8")
        unreleased, released = text.split("## [1.0.0]")
        self.assertIn("### Added\n\n* New thing.", unreleased)
        self.assertNotIn("New thing", released)

    def test_keep_leaves_the_fragments_and_the_result_is_independent_of_creation_order(self):
        self.add("b.fixed.md", "B")
        self.add("a.fixed.md", "A")
        cf.assemble(self.dir, self.log, keep=True)
        self.assertEqual(len(list(self.dir.glob("*.md"))), 2)
        first = self.log.read_text(encoding="utf-8")
        self.log.write_text(BASE, encoding="utf-8")
        for p in self.dir.glob("*.md"):
            p.unlink()
        self.add("a.fixed.md", "A")
        self.add("b.fixed.md", "B")
        cf.assemble(self.dir, self.log, keep=True)
        self.assertEqual(first, self.log.read_text(encoding="utf-8"))

    def test_invalid_fragments_stop_assembly_before_anything_changes(self):
        self.add("1.fixed.md", "Good.")
        self.add("oops.md", "Bad name.")
        with self.assertRaises(SystemExit):
            cf.assemble(self.dir, self.log)
        self.assertEqual(self.log.read_text(encoding="utf-8"), BASE)
        self.assertEqual(len(list(self.dir.glob("*.md"))), 2)

    def test_a_changelog_without_an_unreleased_section_is_refused(self):
        self.log.write_text("# Changelog\n\n## [1.0.0]\n", encoding="utf-8")
        self.add("1.fixed.md", "x")
        with self.assertRaises(SystemExit):
            cf.assemble(self.dir, self.log)


if __name__ == "__main__":
    unittest.main()
