# 002 — LSH parameters and tier thresholds are not user-configurable

## Status
Accepted

## Context

CloneScout's duplicate detection is controlled by six numeric parameters:
three LSH parameters (`num_bands`, `band_size`, `seed`) and three per-tier
Jaccard thresholds (`T1`, `T2`, `T3`).  A natural question is whether these
should be exposed in `clonescout.toml` and on the command line.

## Decision

These parameters are hardcoded as constants in `constants.py` and are not
exposed in the config file or the CLI.

## Reasons

**1. No real-world experience yet.**  The defaults were chosen from theoretical
properties of LSH and reasonable intuition, not from observed behaviour on
real data.  Exposing tuneable knobs before the first release creates an
illusion of control without evidence that the knobs are the right ones or that
the defaults need overriding.

**2. First-release feedback may require rethinking the model.**  If analysis
of real scan results reveals that the tier structure, the feature components,
or the matching strategy need revision, the parameter surface would change too.
Locking in a public config API now increases the cost of that revision.

**3. Config and CLI must stay in sync.**  CloneScout's established pattern is
that every config file key has a corresponding CLI flag (or a deliberate ADR
explaining why it does not).  Adding six parameters to `ReportConfig` would
require either adding six CLI flags or writing a separate ADR to justify the
exception.  Neither is a good use of time at this stage.

## Consequences

- `commands/report.py` reads `LSH_NUM_BANDS`, `LSH_BAND_SIZE`, `LSH_SEED`,
  and `TIER_THRESHOLDS` directly from `constants.py`.
- `ReportConfig` requires no new fields for this purpose.
- When real-world experience justifies exposure, the work is: add fields to
  `ReportConfig`, add validation, add CLI flags, update `commands/report.py`,
  update the sample config, write tests.  The scope is well-defined and can be
  planned as a discrete feature.