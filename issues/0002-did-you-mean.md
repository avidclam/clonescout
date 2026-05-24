# fix: restrict "did you mean" suggestion to long-form config keys

## Problem

The "did you mean" hint is currently shown for all unknown config keys, including
single-character short-form keys like `-c` or `-v`. For these, the Levenshtein
nearest-neighbour result is meaningless — the suggestion is essentially random noise.

## Root cause

The suggestion logic does not distinguish between short-form keys (single dash,
single character) and long-form keys (double dash, full word). It fires whenever
a close enough match exists, regardless of whether the key is a word or an abbreviation.

## Fix

Only offer a suggestion when the unknown key starts with `--`. Short-form keys (`-x`)
get the error message without a suggestion.

## Change

One condition added in `config.py`. No new constants needed.

## Acceptance criteria

- Unknown long-form key `--rrot` → `error: unknown config key '--rrot' — did you mean '--root'?`
- Unknown short-form key `-x` → `error: unknown config key '-x'` (no suggestion)
- Existing tests for the suggestion path continue to pass
- New test: unknown short-form key produces error without suggestion
