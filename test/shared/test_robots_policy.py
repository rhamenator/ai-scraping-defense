from pathlib import Path

import pytest

from src.shared import robots_policy as policy


@pytest.mark.parametrize(
    "rules,path,blocked",
    [
        ("Disallow: /api/metrics # comment", "/api/metrics", True),
        ("Disallow: /Admin/", "/Admin/", True),
        ("Disallow: /Admin/", "/admin/", False),
        ("Disallow: /admin/", "/Admin/", False),
        ("Disallow: /admin/", "/%61dmin/", True),
        ("Disallow: /%61dmin/", "/admin/", True),
        ("Disallow: /a%2fb", "/a%2Fb", True),
        ("Disallow: /a%2fb", "/a/b", False),
        ("Disallow: /a/b", "/a%2Fb", False),
        ("Disallow: /", "/", True),
        ("Disallow: /", "/anything", True),
        ("Disallow: /", "/robots.txt", False),
        ("Disallow: /", "/robots.txt?v=1", False),
        ("Disallow: /\nAllow: /public/", "/public/page", False),
        ("Allow: /same\nDisallow: /same", "/same", False),
        # The "$" end anchor counts toward specificity (RFC 9309), in either rule order.
        ("Allow: /private\nDisallow: /private$", "/private", True),
        ("Disallow: /private$\nAllow: /private", "/private", True),
        ("Allow: /private\nDisallow: /private$", "/private/doc", False),
        ("Disallow: /private\nAllow: /private$", "/private", False),
        ("Disallow: /private\nAllow: /private$", "/private/doc", True),
        ("Allow: /a*\nDisallow: /a*b$", "/axb", True),
        ("Allow: /a*\nDisallow: /a*b$", "/axbc", False),
        ("Disallow: /same\nAllow: /same", "/same", False),
        (
            "Disallow: /\nAllow: /public/\nDisallow: /public/private",
            "/public/private",
            True,
        ),
        ("Disallow: /*.gif$", "/example/image.gif", True),
        ("Disallow: /*.gif$", "/example/image.gif?v=1", False),
        ("Disallow: /a*b*c$", "/abxbbc", True),
        ("Disallow: /literal%2A", "/literal*", True),
        ("Disallow: /literal%24", "/literal$", True),
        ("Disallow: /café", "/caf%C3%A9", True),
        ("Disallow: /caf%C3%A9", "/café", True),
        ("Disallow: /search?q=private", "/search?q=private", True),
        ("Disallow: /admin/", "/admin", False),
        ("Disallow: \nAllow: ", "/anything", False),
    ],
)
def test_rule_semantics(rules, path, blocked):
    assert (
        policy.is_disallowed(policy.parse("User-agent: *\n" + rules), path) == blocked
    )


def test_groups_bom_directive_case_and_empty_groups():
    groups = policy.parse(
        "\ufeffUSER-AGENT : *\rDISALLOW : / # comment\r"
        "User-agent: OtherBot\rUser-agent: ExampleBot\rDisallow: /one\r"
        "User-agent: EXAMPLEBOT\rSitemap: https://example.test/map\rDisallow: /two\r"
        "User-agent: EmptyBot\r"
    )
    assert policy.is_disallowed(groups, "/one", "ExampleBot/1.0")
    assert policy.is_disallowed(groups, "/two", "ExampleBot/1.0")
    assert not policy.is_disallowed(groups, "/public", "ExampleBot/1.0")
    assert policy.is_disallowed(groups, "/public", "FakeExampleBot")
    assert not policy.is_disallowed(groups, "/one", "EmptyBot")
    assert not policy.is_disallowed(policy.parse("Disallow: /"), "/anything")


def test_shipped_policy_preserves_permitted_path_controls():
    root = Path(__file__).resolve().parents[2]
    groups = policy.parse((root / "config/robots.txt").read_text())
    for ua in ["Firefox", "Googlebot/2.1", "Bingbot/2.0"]:
        for path in ["/admin/", "/api/metrics", "/static/app.js", "/%61dmin/"]:
            assert policy.is_disallowed(groups, path, ua)
        assert not policy.is_disallowed(groups, "/pricing", ua)
