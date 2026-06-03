# docs: unify documentation file naming convention to kebab-case

## Problem

The `docs` directory has accumulated a mix of naming styles: `kebab-case` (`developer-guide.md`), `snake_case` (`analysis_blueprint.md`), and spaces with capital letters (`'LSH and MinHash in Plain English.md'`). This inconsistency complicates CLI operations (requires escaping), breaks seamless navigation, and results in ugly URL escaping (`%20`) in web interfaces.

## Root cause

Absence of a strictly enforced naming convention during the early stage of drafting documentation and blueprints.

## Fix

Standardize all documentation filenames to strict lowercase `kebab-case`. Rename the inconsistent files using `git mv` to preserve git history, and audit/update any internal cross-references between documents.

## Change

- `docs/'LSH and MinHash in Plain English.md'` → `docs/lsh-minhash-plain-english.md`
- `docs/blueprints/analysis_blueprint.md` → `docs/blueprints/analysis-blueprint.md`
- `docs/blueprints/cli_config.md` → `docs/blueprints/cli-config.md`
- `docs/blueprints/scan_blueprint.md` → `docs/blueprints/scan-blueprint.md`
- Update internal links in `AGENTS.md`, `developer-guide.md` or blueprints if they point to the renamed files.
- Update "## Project Structure" section in `AGENTS.md`
- Introduce a section in the `developer-guide.md` file that specifies the use of `kebab-case` naming style

## No Change Needed
- `docs/developer-guide.md`
- `docs/blueprints/merge-blueprint.md`
- `docs/decisions/` folder as `001-no-github-issues.md` already conforms to the required style

## Acceptance criteria

- All files in `docs/` and `docs/blueprints/` use only lowercase letters, numbers, and hyphens.
- No spaces or underscores in filenames
- All internal markdown links between documents are verified and working.
- Git history for the renamed files is preserved (`git log --follow` works).