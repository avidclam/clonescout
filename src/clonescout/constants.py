"""Global constants for CloneScout."""

DEFAULT_CONFIG_FILENAME: str = "clonescout.toml"
VERBOSITY_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})

SCAN_PROGRESS_INTERVAL: int = 10_000

CLONESCOUT_VERSION: str = "2026.05"

EXIT_SUCCESS: int = 0
EXIT_BAD_ARGS: int = 1
EXIT_RUNTIME_ERROR: int = 2

TIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T1": ("folder_name", "stem", "ext", "size"),
    "T2": ("stem", "ext", "size", "mtime"),
    "T3": ("stem", "ext", "size"),
}
TIER_ORDER: list[str] = ["T1", "T2", "T3"]
TIER_THRESHOLDS: dict[str, float] = {"T1": 0.80, "T2": 0.70, "T3": 0.60}

LSH_NUM_BANDS: int = 15
LSH_BAND_SIZE: int = 8
LSH_SEED: int = 42
