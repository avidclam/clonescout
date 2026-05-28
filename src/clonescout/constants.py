"""Global constants for CloneScout."""

DEFAULT_CONFIG_FILENAME: str = "clonescout.toml"
VERBOSITY_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})

SCAN_PROGRESS_INTERVAL: int = 10_000

CLONESCOUT_VERSION: str = "2026.05"

EXIT_SUCCESS: int = 0
EXIT_BAD_ARGS: int = 1
EXIT_RUNTIME_ERROR: int = 2
