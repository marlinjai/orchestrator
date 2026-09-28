from textkit.strings import word_count


def test_examples():
    assert word_count("") == 0
    assert word_count("Hello, world!") == 2
    assert word_count("don't stop") == 2
    assert word_count("a1 b2--c3") == 3
    assert word_count("   ") == 0


def test_unicode_letters():
    assert word_count("über café") == 2


def test_separators_and_newlines():
    assert word_count("one\ntwo\tthree") == 3
    assert word_count("x.y,z;w") == 4
    assert word_count("it's 2024's") == 2
