# feat: implement CLI argument parsing and config loading in `cli.py` and `config.py`

## Goal

Implement argument parsing, TOML config loading, CLI/config merging, and the
`Config` class hierarchy as specified in `docs/blueprints/cli_config.md`.

## Modules to create

- `src/clonescout/__main__.py`
- `src/clonescout/cli.py`
- `src/clonescout/config.py`

## Desired public API

```python
# cli.py
def main() -> None: ...

# config.py
def load_config(path: Path | None, command: str) -> BaseConfig: ...

@dataclass class BaseConfig: ...
@dataclass class ScanConfig(BaseConfig): ...
@dataclass class MergeConfig(BaseConfig): ...
@dataclass class ReportConfig(BaseConfig): ...
```

## Requirements

### Argument parser

- Global flags: `-c/--config`, `-f/--force`, `-v`, `-vv`, `-q`
- Commands: `scan`, `merge`, `report`, `sample` (with subcommands `config`, `config --minimal`, `report`)
- No command or `--help`: print help, suggest `sample config`
- All logging → stderr; `report` Markdown and `sample` output → stdout
- Exit codes: 0 success, 1 bad args/config, 2 runtime error

### CLI / config merging

- Scalar flags override their config counterpart when present
- List flags (`--root`, `--skip`, `--exclude`, `--input`) accumulate among themselves, but replace — rather than extend — the config list

### Config classes

- All `@dataclass`, validation in `__post_init__`
- Unknown TOML keys: hard error naming the offending key (best-effort "did you mean?" suggestion)
- Only the section relevant to the active command is validated
- Field defaults and validation rules as specified in `docs/blueprints/cli_config.md`

### DEBUG logging

- After CLI/config merge, if effective verbosity is DEBUG, log the full `Config` object (all fields) to stderr

### `sample` command

- `sample config`: read and print `src/clonescout/data/sample_config.toml`
- `sample config --minimal`: strip full-line comments (lines where `#` is the first non-whitespace character), inline comments (trailing `# …` on a `key = value` line), collapse runs of blank lines to a single blank line

## Tests

- Smoke test: `main()` with `--help` exits 0
- Scalar CLI flag overrides config value
- List CLI flag replaces (not extends) config list
- Unknown TOML key exits 1 with descriptive message
- Missing config file is not an error
- `ScanConfig` with empty `root` after merge exits 1
- `MergeConfig` with fewer than two `input` paths exits 1
- `sample config` prints the `.toml` file unchanged
- `sample config --minimal` removes all comments and collapses blank lines

## Out of scope

- Actual scan, merge, report logic
- `constants.py` beyond what config validation requires