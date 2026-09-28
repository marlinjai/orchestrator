---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Add a `count` command line: `python -m textkit count <path>`

Add `textkit/__main__.py` so that `python3 -m textkit count <path>` reads the file
(UTF-8) and prints one line with three integers separated by single spaces:
the number of lines, the number of whitespace-separated words, and the number of
characters. Lines are counted like `str.splitlines()`. Exit code 0 on success.

If the file does not exist, print an error message to stderr, print nothing to
stdout and exit with code 2. If the command is not `count` or the path is missing,
exit with code 2 as well (an `argparse` usage error is fine).

Example: for a file containing `"one two\nthree\n"` it prints `2 3 14`.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
