# ADR 003 — Naming convention for Vocabulary-related variables

## Status
Accepted

## Context

CloneScout uses two related but distinct representations of the string
vocabulary:

- `Vocabulary` — the class defined in `storage.py`, which maintains a
  bidirectional mapping between strings and integer indices.
- `list[str]` — the plain ordered list of strings, as produced by
  `Vocabulary.as_list()` and stored in `vocab.json` inside every metadata ZIP.

Both representations appear in the codebase, sometimes in the same function.
Without a clear naming convention, a variable named `vocab` could refer 
to either type, which is a source of confusion — especially for
AI coding agents that cannot rely on IDE type inference.

## Decision

The following naming rules apply throughout the codebase:

| Type | Variable name |
|---|---|
| `Vocabulary` | `vocabulary` |
| `list[Vocabulary]` | `vocabularies` |
| `list[str]` (flattened vocabulary) | `vocab` |

The serialised form on disk is `vocab.json` — consistent with the `list[str]`
convention, since JSON cannot represent the `Vocabulary` object directly.

## Consequences

- `build_folders(vocab: list[str], ...)` — parameter name is `vocab`.
- In `commands/report.py`: the return value of `read_zip` is unpacked as
  `vocabulary, metadata, info = read_zip(...)`, then passed as
  `build_folders(vocabulary.as_list(), metadata)`.
- Any future function that accepts a `Vocabulary` object uses `vocabulary`
  as the parameter name, never `vocab`.
- Code review and agent instructions should treat a `vocab: Vocabulary`
  annotation (or a `vocabulary: list[str]` annotation) as a naming error
  requiring correction.