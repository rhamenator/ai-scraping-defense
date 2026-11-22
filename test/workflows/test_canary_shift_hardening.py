"""Guards the hardening of .github/workflows/canary-shift.yml (#1909)."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "canary-shift.yml"


def _text() -> str:
    return WORKFLOW.read_text()


def _run_blocks(text: str) -> list[str]:
    blocks, current, indent = [], None, 0
    for line in text.splitlines():
        if current is not None:
            if line.strip() == "" or len(line) - len(line.lstrip()) > indent:
                current.append(line)
                continue
            blocks.append("\n".join(current))
            current = None
        match = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if match:
            current, indent = [], len(match.group(1))
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def test_job_runs_in_the_protected_production_environment():
    assert re.search(r"(?m)^    environment: production\s*$", _text())


def test_no_workflow_expression_is_interpolated_into_shell_source():
    blocks = _run_blocks(_text())
    assert blocks, "expected run blocks"
    for block in blocks:
        assert "${{" not in block, block


def test_namespace_and_ingress_are_fixed_not_inputs():
    text = _text()
    inputs = text.split("permissions:")[0]
    assert "namespace" not in inputs
    assert "canary_ingress" not in inputs
    assert re.search(r"(?m)^      CANARY_NAMESPACE: production\s*$", text)
    assert re.search(r"(?m)^      CANARY_INGRESS: ai-scraping-defense-canary\s*$", text)


def test_weight_is_validated_as_a_whole_number_up_to_100():
    text = _text()
    assert "^[0-9]+$" in text
    assert "CANARY_WEIGHT > 100" in text
