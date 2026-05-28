# Developer Guide — CloneScout

---

## Testing

**Framework:** `pytest` (optional dev dependency).

- Integration tests build `.zip` and `.tar.gz` archives **on the fly** via
  `tmp_path` — no binary fixtures committed to the repo.
- Every module's public API should have at least a smoke test.
- Core logic (scanning, merging, analysis) should have positive-path + edge-case tests.

```bash
.venv/bin/python -m pytest tests/ -v
```

---

## Git Conventions

Lightweight conventional commits:

| Prefix | Use |
|---|---|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation changes |
| `refactor:` | Restructuring without behavior change |
| `test:` | Adding or updating tests |
| `chore:` | Build scripts, CI, tool config |

Example: `feat: add LSH banding for T1 tier matching`

Branch naming follows similar prefix convention: `feature/<slug>`, where `<slug>`
is part of the corresponding file in `issues/`: `issues/${slug}.md`.
Example: `feature/0001-cli-config.md`.
The `issue-start` helper creates branches with this prefix automatically.

---

## Versioning

CalVer: `2026.05`, `2026.06`, etc.

---

## Build

```bash
.venv/bin/python scripts/build_zipapp.py
```

Which runs:

```bash
.venv/bin/python -m zipapp src/clonescout \
    -o dist/clonescout-2026-05.pyz \
    -m "clonescout.__main__:main" \
    -p "/usr/bin/env python3"
```

Output: `dist/clonescout-2026-05.pyz`. No Makefile.

---

## Day-to-Day

```bash
.venv/bin/python -m ruff check src/    # lint
.venv/bin/python -m mypy src/          # type check
.venv/bin/python -m pytest tests/ -v   # test
.venv/bin/python scripts/build_zipapp.py  # build
```

---

## Ruff Config (`pyproject.toml`)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "SIM", "TCH"]
```

## Shell Workflow Helpers

The file `scripts/git-workflow.sh` provides three shell functions for working with
GitHub Issues and feature branches: `issue-start`, `issue-status`, and `issue-finish`.

### Setup

The setup relies on a convention in `~/.bashrc` that auto-sources every `*.sh` file
from `~/.bash_functions_d/` at shell startup:

    # Dynamically load all custom functions from the functions directory
    if [ -d ~/.bash_functions_d ]; then
        for func_file in ~/.bash_functions_d/*.sh; do
            [ -e "$func_file" ] && . "$func_file"
        done
        unset func_file
    fi

If this block is not yet in your `~/.bashrc`, add it first.

Then create a symbolic link from that directory into the project:

    ln -s "$(pwd)/scripts/git-workflow.sh" ~/.bash_functions_d/clonescout-git.sh

Run this once from the project root. Because it's a symlink (not a copy), the helpers
stay in sync with the project automatically on every `git pull`.

Reload your shell to activate:

    source ~/.bashrc

### Prerequisites

- `gh` (GitHub CLI) must be installed and authenticated (`gh auth login`)
- Issues are stored under `issues/<slug>.md` in the project root