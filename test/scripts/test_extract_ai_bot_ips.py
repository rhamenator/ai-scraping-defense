from scripts.extract_ai_bot_ips import extract_counts, is_ai_crawler


def test_extracts_unique_valid_ips_from_caddy_json_lines():
    lines = [
        '{"request":{"client_ip":"203.0.113.5","headers":{"User-Agent":["GPTBot/1.0"]}}}',
        '{"request":{"client_ip":"203.0.113.5","headers":{"user-agent":["ClaudeBot"]}}}',
        '{"request":{"remote_ip":"2001:db8::7","headers":{"User-Agent":["PerplexityBot"]}}}',
        '{"request":{"remote_ip":"198.51.100.9","headers":{"User-Agent":["Mozilla/5.0"]}}}',
    ]

    assert extract_counts(lines) == {"203.0.113.5": 2, "2001:db8::7": 1}


def test_ignores_invalid_json_and_invalid_addresses(capsys):
    lines = [
        "not-json",
        '{"request":{"remote_ip":"not-an-ip","headers":{"User-Agent":["GPTBot"]}}}',
    ]

    assert not extract_counts(lines, "access.log")
    assert "access.log:1: invalid JSON" in capsys.readouterr().err


def test_matches_tokens_case_insensitively():
    assert is_ai_crawler("Mozilla/5.0 compatible; OAI-SearchBot/1.0")
    assert not is_ai_crawler("Mozilla/5.0")
