from orchestrator.parse import parse_frontmatter


def test_no_frontmatter_returns_empty():
    assert parse_frontmatter("# Goal\n\njust text") == {}


def test_scalar_keys():
    text = '---\ntask: my-task\nspec: path/to/spec.md\n---\n# Goal\n'
    fm = parse_frontmatter(text)
    assert fm["task"] == "my-task"
    assert fm["spec"] == "path/to/spec.md"


def test_quoted_scalar():
    text = '---\nmarlin_proxy: "shadow"\n---\n'
    assert parse_frontmatter(text)["marlin_proxy"] == "shadow"


def test_inline_list():
    text = "---\ndepends_on: [a, b, c]\n---\n"
    assert parse_frontmatter(text)["depends_on"] == ["a", "b", "c"]


def test_nested_map():
    text = (
        "---\n"
        "marlin_proxy: live\n"
        "marlin_proxy_categories:\n"
        "  branch_cleanup: shadow\n"
        "  status_fetch: live\n"
        "---\n"
    )
    fm = parse_frontmatter(text)
    assert fm["marlin_proxy"] == "live"
    assert fm["marlin_proxy_categories"] == {
        "branch_cleanup": "shadow",
        "status_fetch": "live",
    }


def test_comments_ignored():
    text = "---\ntask: t\n# this is a comment\nspec: s\n---\n"
    fm = parse_frontmatter(text)
    assert fm == {"task": "t", "spec": "s"}
