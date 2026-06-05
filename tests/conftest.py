"""Shared test data and fixtures for clone scout tests."""

from __future__ import annotations

from typing import Any

# Smoke-test vocabulary produced by clonescout scan + merge on two machines
# (see snippets/analysis_snippet.py for the full explanation).
SMOKE_VOCAB: list[str] = [
    "",           # 0  — POSIX anchor
    "A:", "B:", "C:", "D:", "E:", "F:", "G:", "H:", "I:", "J:", "K:", "L:", "M:",
    "N:", "O:", "P:", "Q:", "R:", "S:", "T:", "U:", "V:", "W:", "X:", "Y:", "Z:",
    # 27 onward — strings encountered during scan
    "smoke/Users/alice",            # 27
    "contracts",                    # 28
    ".pdf",                         # 29
    "contract_2020",                # 30
    "contract_2021",                # 31
    "smoke/Users/alice/photos",     # 32
    "2021",                         # 33
    ".jpg",                         # 34
    "IMG_001",                      # 35
    "IMG_002",                      # 36
    "IMG_003",                      # 37
    "IMG_004",                      # 38
    "IMG_005",                      # 39
    "smoke/backup/photos",          # 40
    "2021_copy",                    # 41
    ".png",                         # 42
    "THUMB",                        # 43
]


# Smoke-test metadata (integer keys, as returned by storage.read_zip).
SMOKE_METADATA: dict[Any, Any] = {
    "windows": {
        3: {                        # anchor = "C:"
            27: {                   # folder_parent = "smoke/Users/alice"
                28: {               # folder_name = "contracts"
                    29: {           # suffix = ".pdf"
                        30: ("PDF", 8192,  1780599591),  # contract_2020
                        31: ("PDF", 9216,  1780599604),  # contract_2021
                    }
                }
            },
            32: {                   # folder_parent = "smoke/Users/alice/photos"
                33: {               # folder_name = "2021"
                    34: {           # suffix = ".jpg"
                        35: ("JPG", 1024, 1780599691),   # IMG_001
                        36: ("JPG", 2048, 1780599698),   # IMG_002
                        37: ("JPG", 3072, 1780599708),   # IMG_003
                        38: ("JPG", 4096, 1780599715),   # IMG_004
                        39: ("JPG", 5120, 1780599725),   # IMG_005
                    }
                }
            }
        }
    },
    "linux": {
        0: {                        # anchor = "" (POSIX)
            40: {                   # folder_parent = "smoke/backup/photos"
                41: {               # folder_name = "2021_copy"
                    34: {           # suffix = ".jpg"
                        35: ("JPG", 1024, 1780606892),   # IMG_001
                        36: ("JPG", 2048, 1780606900),   # IMG_002
                        37: ("JPG", 3072, 1780606910),   # IMG_003
                        38: ("JPG", 4096, 1780606916),   # IMG_004
                        39: ("JPG", 5120, 1780606926),   # IMG_005
                    },
                    42: {           # suffix = ".png"
                        43: ("PNG",  512, 1780600161),   # THUMB
                    }
                }
            }
        }
    }
}
