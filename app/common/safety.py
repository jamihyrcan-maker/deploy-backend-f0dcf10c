from __future__ import annotations

import os


def safe_mode_enabled() -> bool:
    """
    SAFE_MODE=1 blocks vendor task creation.
    """
    return os.getenv("SAFE_MODE", "1").strip() not in ("", "0", "false", "False")

