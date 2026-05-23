# Blueprint: CLI & Config — CloneScout

> Specification for `cli.py`, `__main__.py`, and `config.py`.

---

## `__main__.py`

Entry point for `python -m clonescout` and the `.pyz` distribution. Just calls `main()` from `cli.py`:

```python
from clonescout.cli import main

if __name__ == "__main__":
    main()
```

---

## `cli.py`

Owns argument parsing, config loading, CLI/config merging, and command dispatch.

### Structure

```
main()
├── build_parser()        # returns the top-level ArgumentParser
├── setup_logging()       # applies verbosity flags to logging
├── load_and_merge()      # loads TOML, merges CLI overrides, returns Config subclass
└── dispatch:
    ├── cmd_scan()
    ├── cmd_merge()
    ├── cmd_report()
    └── cmd_sample()
```

### Argument Parser Layout

```
clonescout [-c PATH] [-f] [-v | -vv | -q] <command> [command flags]

Global flags (before command):
  -c, --config PATH     Config file. Default: clonescout.toml in CWD
  -f, --force           Overwrite existing output files
  -v                    INFO verbosity
  -vv                   DEBUG verbosity
  -q                    ERROR verbosity

Commands:
  scan                  Collect metadata, write ZIP
  merge                 Merge metadata ZIPs
  report                Analyze and report duplicates
  sample                Print sample output (see subcommands)

sample subcommands:
  config                Full annotated clonescout.toml
  config --minimal      Same, without comments
  report                Example Markdown report
```

No command (or `--help`): print help, suggest running `sample config`.

### CLI / Config Merging Rules

`cli.py` calls `config.py` to parse TOML, then applies overrides:

- Scalar flags (`--node`, `--output`, etc.) override their config counterpart when present.
- List flags (`--root`, `--skip`, `--exclude`, `--input`) replace the config list entirely when one or more values are given on the command line. They accumulate among themselves, but replace — rather than extend — the config list.
- Missing config file is not an error — config is built from CLI args and defaults only.

### Streams

| Output | Stream |
|---|---|
| All logging | stderr |
| `report` Markdown | stdout |
| `sample` output | stdout |

### Exit Codes

| Situation | Code |
|---|---|
| Success | 0 |
| Bad arguments or config error | 1 |
| Runtime error (scan failure, unreadable archive, etc.) | 2 |

---

## `config.py`

Owns TOML parsing and the Config class hierarchy. Does not own CLI merging.

### Responsibilities

- Read and parse `clonescout.toml` (or the file given via `--config`)
- Reject unknown TOML keys with a hard error naming the offending key
- Instantiate and return the appropriate `Config` subclass
- Validate eagerly — all validation happens at load time, before any work starts

### Factory Function

```python
def load_config(path: Path | None, command: str) -> BaseConfig:
    """Parse TOML config file and return the appropriate Config subclass.

    Args:
        path: Path to the TOML file, or None if no config file is present.
        command: Active command name ('scan', 'merge', 'report').

    Returns:
        A fully populated and validated Config subclass instance.

    Raises:
        SystemExit(1): On unknown keys, type errors, or invalid values.
    """
```

Only the section relevant to `command` is validated. A missing `[merge]` section is
not an error when running `scan`.

### Class Hierarchy

```
BaseConfig
├── ScanConfig(BaseConfig)
├── MergeConfig(BaseConfig)
└── ReportConfig(BaseConfig)
```

All are `@dataclass` classes. Validation lives in `__post_init__`.

### `BaseConfig`

```python
@dataclass
class BaseConfig:
    force: bool = False
    verbosity: str = "WARNING"
```

### `ScanConfig(BaseConfig)`

| Field | Type | Default | Notes |
|---|---|---|---|
| `node` | `str` | `""` | Resolved to `socket.gethostname()` in `__post_init__` if empty |
| `root` | `list[str]` | — | Hard error if empty after merge with CLI |
| `skip` | `list[str]` | `[]` | Exact directory names |
| `exclude` | `list[re.Pattern]` | `[]` | Compiled in `__post_init__`; hard error if any pattern is invalid |
| `output` | `str` | — | Hard error if not set |

### `MergeConfig(BaseConfig)`

| Field | Type | Default | Notes |
|---|---|---|---|
| `input` | `list[str]` | — | Hard error if fewer than two paths after merge with CLI |
| `output` | `str` | — | Hard error if not set |

### `ReportConfig(BaseConfig)`

| Field | Type | Default | Notes |
|---|---|---|---|
| `input` | `str` | — | Defaults to `merge.output` if present in config; hard error otherwise |
| `output` | `str` \| `None` | `None` | If None, report goes to stdout |

### Defaults Policy

- Simple scalars: field defaults on the dataclass.
- Computed defaults (e.g. hostname): resolved in `__post_init__`.
- Shared constants (default config filename, supported extensions): in `constants.py`.

### Unknown Keys

Any key present in the TOML file that is not recognised for the active command
is a hard error:

```
error: unknown config key 'rrot' in [scan] — did you mean 'root'?
```

Suggestion ("did you mean") is best-effort, not required.

---

## `sample config` Source

`sample config` reads and prints `src/clonescout/data/sample_config.toml` from
the package. This file is the single source of truth for all config documentation.

`sample config --minimal` strips the same file at runtime: 
remove full-line comments (lines where # is the first non-whitespace character), 
inline comments (trailing # … on a key = value line), 
collapse runs of blank lines to a single blank line. No separate file.
