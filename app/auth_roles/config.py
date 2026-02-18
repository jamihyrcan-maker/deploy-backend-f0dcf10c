from __future__ import annotations

import os
from typing import Dict, Optional

# Role order (higher can do lower)
_ROLE_RANK = {"monitor": 1, "operator": 2, "admin": 3}

# Optional DEV fallback keys (disabled by default)
DEFAULT_KEYS = {
    "dev-monitor-key": "monitor",
    "dev-operator-key": "operator",
    "dev-admin-key": "admin",
}


def _load_keys_from_env() -> Dict[str, str]:
    """
    Supported env vars:
      API_KEY_MONITOR, API_KEY_OPERATOR, API_KEY_ADMIN
    """
    keys: Dict[str, str] = {}
    mon = os.getenv("API_KEY_MONITOR")
    op = os.getenv("API_KEY_OPERATOR")
    adm = os.getenv("API_KEY_ADMIN")

    if mon:
        keys[mon] = "monitor"
    if op:
        keys[op] = "operator"
    if adm:
        keys[adm] = "admin"
    return keys


def _load_keys_from_secrets() -> Dict[str, str]:
    """
    Optional app/secrets.py can define:
      API_KEYS = {"key1": "operator", "key2": "monitor", ...}
      or API_KEY_MONITOR / API_KEY_OPERATOR / API_KEY_ADMIN
    """
    try:
        from .. import secrets  # type: ignore
    except Exception:
        return {}

    keys: Dict[str, str] = {}

    api_keys = getattr(secrets, "API_KEYS", None)
    if isinstance(api_keys, dict):
        for k, v in api_keys.items():
            if isinstance(k, str) and isinstance(v, str):
                keys[k] = v.lower().strip()

    for env_name, role in [
        ("API_KEY_MONITOR", "monitor"),
        ("API_KEY_OPERATOR", "operator"),
        ("API_KEY_ADMIN", "admin"),
    ]:
        val = getattr(secrets, env_name, None)
        if isinstance(val, str) and val.strip():
            keys[val.strip()] = role

    return keys


def get_api_keys() -> Dict[str, str]:
    keys: Dict[str, str] = {}
    keys.update(_load_keys_from_secrets())
    keys.update(_load_keys_from_env())

    # Security-first default for deployment: no fallback keys unless explicitly enabled.
    if not keys and os.getenv("ALLOW_DEFAULT_API_KEYS", "0") == "1":
        keys.update(DEFAULT_KEYS)

    norm: Dict[str, str] = {}
    for k, role in keys.items():
        r = (role or "").lower().strip()
        if r not in _ROLE_RANK:
            continue
        norm[k] = r
    return norm


def role_allows(user_role: str, required_role: str) -> bool:
    return _ROLE_RANK.get(user_role, 0) >= _ROLE_RANK.get(required_role, 0)


def get_role_for_key(api_key: str) -> Optional[str]:
    if not api_key:
        return None
    keys = get_api_keys()
    return keys.get(api_key)
