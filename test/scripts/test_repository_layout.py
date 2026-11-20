"""Keep generated snapshots out of the documented repository entry points."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_has_no_obsolete_generated_snapshots():
    obsolete = [
        "models.json",
        "compliance_problems.json",
        "problems.txt",
        "# setup.sh.txt",
        "__init__.py",
    ]
    assert [name for name in obsolete if (ROOT / name).exists()] == []


def test_build_entry_points_and_documented_data_remain_available():
    for name in ["ai-scraping-defense.sln", "rust-toolchain.toml", "LICENSE"]:
        assert (ROOT / name).is_file()
    assert (ROOT / "docs/triage/problem_file_map.json").is_file()
    assert (ROOT / "docs/triage/issue_milestone_assignments.json").is_file()
    assert (
        ROOT / "docs/presentations/AI_Scraping_Defense_System_Presentation.pptx"
    ).is_file()


def test_problem_generator_finds_relocated_input_catalogue():
    import runpy

    generator = runpy.run_path(str(ROOT / "scripts/generate_problem_file_map.py"))
    problems = generator["load_problems"]()
    assert problems
    assert any(item["problem"] == "No GDPR Compliance Framework" for item in problems)
