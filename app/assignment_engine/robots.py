from __future__ import annotations

import os
from typing import List

def get_robot_ids() -> List[str]:
    """
    Robot registry v0:
      - Prefer env var ROBOT_IDS="id1,id2,id3"
      - Else try backend/app/secrets.py ROBOT_IDS or ROBOT_IDS_CSV
      - Else fallback [] (you must set one of the above)
    """
    env_csv = os.getenv("ROBOT_IDS", "").strip()
    if env_csv:
        return [x.strip() for x in env_csv.split(",") if x.strip()]

    try:
        from .. import secrets  # type: ignore
        if hasattr(secrets, "ROBOT_IDS") and isinstance(secrets.ROBOT_IDS, list):
            return [str(x).strip() for x in secrets.ROBOT_IDS if str(x).strip()]
        if hasattr(secrets, "ROBOT_IDS_CSV"):
            csv = str(secrets.ROBOT_IDS_CSV).strip()
            if csv:
                return [x.strip() for x in csv.split(",") if x.strip()]
    except Exception:
        pass

    return []
