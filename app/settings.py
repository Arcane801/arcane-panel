"""
Arcane Panel — Settings Manager
"""
import json
import time
from typing import Any, Dict, Optional

from .storage import get_db, log_audit


DEFAULT_SETTINGS = {
    "lang": "fa",
    "theme": "dark",
    "public_domain": "",
    "keep_alive": True,
    "transport": "ws",
    "fingerprint": "chrome",
    "alpn": "http/1.1",
    "sni_override": "",
    "fragment_enabled": True,
    "fragment_packets": "tlshello",
    "fragment_length": "10-30",
    "fragment_interval": "10-20",
}


async def get_all_settings() -> Dict[str, Any]:
    async with get_db() as db:
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            stored = {row[0]: json.loads(row[1]) for row in rows}
    result = DEFAULT_SETTINGS.copy()
    result.update(stored)
    return result


async def get_setting(key: str, default: Any = None) -> Any:
    settings = await get_all_settings()
    return settings.get(key, default)


async def update_settings(updates: Dict[str, Any], updated_by: Optional[str] = None, ip: Optional[str] = None) -> bool:
    allowed_keys = set(DEFAULT_SETTINGS.keys())
    filtered = {k: v for k, v in updates.items() if k in allowed_keys}
    if not filtered:
        return False
    if "transport" in filtered and filtered["transport"] not in ("ws", "xhttp"):
        raise ValueError("invalid-transport")
    if "fingerprint" in filtered:
        valid_fps = ("chrome", "firefox", "edge", "ios", "random")
        if filtered["fingerprint"] not in valid_fps:
            raise ValueError("invalid-fingerprint")
    async with get_db() as db:
        for key, value in filtered.items():
            await db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), time.time()),
            )
        await db.commit()
    await log_audit(
        action="settings.update", ip=ip, username=updated_by,
        detail=f"keys={list(filtered.keys())}", success=True,
    )
    return True


async def get_domain(request_host: str) -> str:
    public_domain = await get_setting("public_domain")
    if public_domain:
        return public_domain
    if ":" in request_host:
        return request_host.split(":")[0]
    return request_host
