"""
Arcane Panel — User (inbound) management
"""
import time
import uuid as uuid_lib
from typing import Optional, List, Dict, Any

from .storage import get_db, log_audit


async def create_user(
    name: str,
    max_gb: Optional[float] = None,
    expires_at: Optional[float] = None,
    max_requests: Optional[int] = None,
    max_connections: Optional[int] = None,
    ip_lock: Optional[str] = None,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    uid = uuid_lib.uuid4().hex[:12]
    user_uuid = str(uuid_lib.uuid4())
    now = time.time()
    
    async with get_db() as db:
        await db.execute(
            """INSERT INTO users 
            (uid, name, uuid, max_gb, expires_at, max_requests, max_connections, 
             ip_lock, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, name, user_uuid, max_gb, expires_at, max_requests, 
             max_connections, ip_lock, note, now, now),
        )
        await db.commit()
    
    await log_audit(
        action="user.create", ip=ip, username=created_by,
        detail=f"uid={uid} name={name}", success=True,
    )
    
    from .xray import xray_manager
    await xray_manager.reload()
    
    return await get_user(uid)


async def get_user(uid: str) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE uid = ?", (uid,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)


async def list_users() -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_user(uid: str, updates: Dict[str, Any], updated_by: Optional[str] = None, ip: Optional[str] = None) -> bool:
    allowed_fields = {
        "name", "enabled", "max_gb", "expires_at", "max_requests",
        "max_connections", "ip_lock", "note",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return False
    
    filtered["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in filtered.keys())
    values = list(filtered.values()) + [uid]
    
    async with get_db() as db:
        cursor = await db.execute(
            f"UPDATE users SET {set_clause} WHERE uid = ?", values
        )
        await db.commit()
        if cursor.rowcount == 0:
            return False
    
    await log_audit(
        action="user.update", ip=ip, username=updated_by,
        detail=f"uid={uid} fields={list(filtered.keys())}", success=True,
    )
    
    if "enabled" in filtered:
        from .xray import xray_manager
        await xray_manager.reload()
    
    return True


async def delete_user(uid: str, deleted_by: Optional[str] = None, ip: Optional[str] = None) -> bool:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM users WHERE uid = ?", (uid,))
        await db.commit()
        if cursor.rowcount == 0:
            return False
    
    await log_audit(
        action="user.delete", ip=ip, username=deleted_by,
        detail=f"uid={uid}", success=True,
    )
    
    from .xray import xray_manager
    await xray_manager.reload()
    
    return True


async def rotate_uuid(uid: str, rotated_by: Optional[str] = None, ip: Optional[str] = None) -> Optional[str]:
    new_uuid = str(uuid_lib.uuid4())
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE users SET uuid = ?, updated_at = ? WHERE uid = ?",
            (new_uuid, time.time(), uid),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
    
    await log_audit(
        action="user.rotate_uuid", ip=ip, username=rotated_by,
        detail=f"uid={uid}", success=True,
    )
    
    from .xray import xray_manager
    await xray_manager.reload()
    
    return new_uuid


async def update_user_stats(uid: str, up_bytes: int, down_bytes: int, ip: Optional[str] = None):
    async with get_db() as db:
        await db.execute(
            """UPDATE users 
            SET used_bytes_up = used_bytes_up + ?,
                used_bytes_down = used_bytes_down + ?,
                request_count = request_count + 1,
                last_seen = ?,
                last_ip = COALESCE(?, last_ip)
            WHERE uid = ?""",
            (up_bytes, down_bytes, time.time(), ip, uid),
        )
        await db.commit()
