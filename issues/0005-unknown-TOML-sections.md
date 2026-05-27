**feat: reject unknown TOML sections with a hard error**

## Problem

Unknown top-level sections in the config file are silently ignored. A user who writes `[scna]` instead of `[scan]` gets no error — the entire section is quietly skipped and defaults are used instead. This directly contradicts the blueprint: "Reject unknown TOML keys with a hard error naming the offending key."

## Root cause

`_extract_globals` skips all dict-valued keys (which is how TOML tables appear after parsing), so unknown sections like `[bogus]` or `[scna]` pass through without validation. Only keys within known sections are checked.

## Fix

After `_extract_globals`, verify that all dict-valued top-level keys are members of the known section set `{"scan", "merge", "report"}`. Any unknown section raises `ConfigError` with the offending name — and a "did you mean" hint if a close match exists.

## Change

- `config.py` — add unknown-section check after `_extract_globals`
- Reuse existing `_suggest` for the hint

## Acceptance criteria

- `[scna]` in config → `error: unknown config section '[scna]' — did you mean '[scan]'?`
- `[bogus]` in config → `error: unknown config section '[bogus]'` (no suggestion if no close match)
- `[scan]`, `[merge]`, `[report]` → accepted as before
- A section not relevant to the active command (e.g. `[merge]` when running `scan`) → accepted without error
- New tests cover typo in section name and completely unknown section name