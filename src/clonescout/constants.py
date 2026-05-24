"""Global constants for CloneScout."""

DEFAULT_CONFIG_FILENAME: str = "clonescout.toml"
VERBOSITY_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})

EXIT_SUCCESS: int = 0
EXIT_BAD_ARGS: int = 1
EXIT_RUNTIME_ERROR: int = 2
