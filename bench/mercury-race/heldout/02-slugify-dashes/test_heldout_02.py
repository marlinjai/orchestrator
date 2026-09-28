from textkit.strings import slugify


def test_examples():
    assert slugify("  Hello,  World!! ") == "hello-world"
    assert slugify("a--b") == "a-b"
    assert slugify("!!!") == ""
    assert slugify("") == ""
    assert slugify("Already-Fine") == "already-fine"
    assert slugify("Crème Brûlée") == "cr-me-br-l-e"


def test_digits_kept_and_edges_stripped():
    assert slugify("--Version 2.0--") == "version-2-0"
    assert slugify("abc") == "abc"
