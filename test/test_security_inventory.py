from pathlib import Path

from src.security_audit.inventory import generate_inventory_markdown


def test_security_inventory_matches_snapshot():
    json_path = Path("security_problems_batch1.json")
    output_path = Path("docs/security/security_inventory_batch1.md")

    generated = generate_inventory_markdown(json_path)
    recorded = output_path.read_text()

    assert generated == recorded
