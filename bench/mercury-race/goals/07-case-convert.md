---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Add camelCase and snake_case conversion

Add a new module `textkit/case.py` with:

- `camel_to_snake(name: str) -> str`: `"helloWorld"` gives `"hello_world"`,
  `"HTTPServerError"` gives `"http_server_error"`, `"getX"` gives `"get_x"`,
  `"already_snake"` stays `"already_snake"`, `"Version2Update"` gives
  `"version2_update"`, `""` gives `""`. An acronym is kept together until the last
  capital that starts the next word.
- `snake_to_camel(name: str, upper: bool = False) -> str`: `"http_server_error"`
  gives `"httpServerError"`, with `upper=True` `"HttpServerError"`; repeated,
  leading or trailing underscores are ignored (`"__a__b_"` gives `"aB"`); `""` gives
  `""`.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
