**fix: _suggest regression — "did you mean" silenced for TOML config keys**

## Problem

After issue #0002, the "did you mean" hint no longer works for TOML config key typos. A user who writes `rrot = [...]` in `[scan]` gets a bare error with no suggestion, despite the feature existing specifically for this case.

## Root cause

The `--` prefix guard added in #0002 to suppress noise for short CLI flags (`-x`) was placed in `_suggest` itself — a shared function called from both the CLI parser and the config validator. As a result, TOML keys (which never start with `--`) are always suppressed.

The fix in #0002 was too broad.

## Fix

Move the `--` guard out of `_suggest` and into `_SuggestingParser` — the CLI-only call site. `_suggest` itself becomes context-agnostic: it returns the best match if one exists, or an empty string if the known set is empty or the match is too distant.

## Change

- `config.py` — remove `--` guard from `_suggest`
- `cli.py` — add `--` guard at the call site inside `_SuggestingParser`
- No new constants needed

## Acceptance criteria

- TOML typo `rrot` in `[scan]` → `error: unknown config key 'rrot' in [scan] — did you mean 'root'?`
- TOML typo `outptu` in `[merge]` → `error: unknown config key 'outptu' in [merge] — did you mean 'output'?`
- CLI short flag `-x` → `error: unknown option '-x'` (no suggestion — guard still active in `_SuggestingParser`)
- CLI long flag `--outptu` → `error: unknown option '--ouuput' — did you mean '--output'?`
- Existing tests for #0002 continue to pass
- New tests cover TOML suggestion path