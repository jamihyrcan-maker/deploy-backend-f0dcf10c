from __future__ import annotations

from typing import Optional, Sequence

from fastapi import Depends, Header, HTTPException, status, WebSocket

from .config import get_role_for_key, role_allows


def _deny(detail: str = "Unauthorized"):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _forbidden(detail: str = "Forbidden"):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def get_principal(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    """
    REST auth: require X-API-Key header.
    """
    role = get_role_for_key(x_api_key or "")
    if not role:
        _deny("Missing or invalid X-API-Key")
    return {"role": role, "api_key": x_api_key}


def require_role(*allowed_roles: Sequence[str]):
    """
    Dependency factory:
      - require_role("monitor")  -> monitor+operator+admin
      - require_role("operator") -> operator+admin
      - require_role("admin")    -> admin only
    """
    allowed = [r.lower().strip() for r in allowed_roles if isinstance(r, str)]

    def _dep(principal=Depends(get_principal)):
        user_role = principal["role"]
        # If multiple roles provided, allow if user_role >= ANY of them
        ok = any(role_allows(user_role, r) for r in allowed)
        if not ok:
            _forbidden(f"Requires role: {allowed_roles}")
        return principal

    return _dep


async def ws_require_role(ws: WebSocket, allowed_role: str) -> dict:
    """
    WS auth: allow API key in:
      - query param: ?api_key=...
      - header: X-API-Key
    """
    api_key = ws.query_params.get("api_key") or ws.headers.get("x-api-key") or ""
    role = get_role_for_key(api_key)
    if not role:
        await ws.close(code=1008)  # policy violation
        return {}

    if not role_allows(role, allowed_role):
        await ws.close(code=1008)
        return {}

    return {"role": role, "api_key": api_key}
