**fix: _strip_comments corrupts TOML values containing #**

## Problem

`_strip_comments` naively splits every line on `#` without respecting TOML quoting rules. A value like `pattern = "hello#world"` gets truncated to `pattern = "hello`, producing invalid TOML. The `[scan]` section already accepts regex patterns in `exclude`, and regex patterns containing `#` are a realistic user input — so this is not a hypothetical edge case.

## Root cause

The current implementation:

```python
if "#" in line:
    line = line.split("#", 1)[0].rstrip()
```

treats every `#` as a comment delimiter regardless of whether it appears inside a quoted string.

## Fix

Track whether the current character position is inside a single or double quoted string, and only strip `#` that appears outside quotes. No external dependencies needed — a small state machine over the line characters is sufficient.

## Change

- `cli.py` — rewrite `_strip_comments` to be quote-aware
- No changes to other modules

## Acceptance criteria

- `exclude = ["(?i)/\\.tmp/", "color=#ff0000"]` → parsed correctly, `#ff0000` preserved
- `# full-line comment` → stripped as before
- `output = "file.zip" # trailing comment` → trailing comment stripped, value preserved
- `name = "hello#world" # comment` → value `hello#world` preserved, comment stripped
- Existing tests for `_strip_comments` continue to pass
- New tests cover each of the cases above