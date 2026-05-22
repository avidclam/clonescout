# Developer Guide — CloneScout

---

## Testing

**Framework:** `pytest` (optional dev dependency).

- Integration tests build `.zip` and `.tar.gz` archives **on the fly** via
  `tmp_path` — no binary fixtures committed to the repo.
- Every module's public API should have at least a smoke test.
- Core logic (scanning, merging, analysis) should have positive-path + edge-case tests.

```bash
python3 -m pytest tests/ -v
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

---

## Versioning

CalVer: `2026.05`, `2026.06`, etc.

---

## Build

```bash
python3 scripts/build_zipapp.py
```

Which runs:

```bash
python3 -m zipapp src/clonescout \
    -o dist/clonescout-2026-05.pyz \
    -m "clonescout.__main__:main" \
    -p "/usr/bin/env python3"
```

Output: `dist/clonescout-2026-05.pyz`. No Makefile.

---

## Day-to-Day

```bash
python3 -m ruff check src/    # lint
python3 -m mypy src/          # type check
python3 -m pytest tests/ -v   # test
python3 scripts/build_zipapp.py  # build
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
