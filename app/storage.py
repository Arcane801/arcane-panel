"""
Arcane Panel — SQLite Storage Layer
Async-safe, WAL mode for concurrent reads, atomic writes.
"""
import aiosqlite
import asyncio
import os
import time
import json
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager

from . import config


_init_lock = asyncio.Lock()
_initialized = False


async def _ensure_db() -> aiosqlite.Connection:
    global _initialized
    os.makedirs(config.DATA_DIR, exist_ok=True)
    
    db = await aiosqlite.connect(config.DB_PATH)
    db.row_factory = aiosqlite.Row
    
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")
    
    if not _initialized:
        async with _init_lock:
            if not _initialized:
                await _init_schema(db)
                _initialized = True
    
    return db


async def _init_schema(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at REAL NOT NULL,
            password_version INTEGER NOT NULL DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            uuid TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            max_gb REAL,
            expires_at REAL,
            max_requests INTEGER,
            max_connections INTEGER,
            ip_lock TEXT,
            used_bytes_up INTEGER NOT NULL DEFAULT 0,
            used_bytes_down INTEGER NOT NULL DEFAULT 0,
            request_count INTEGER NOT NULL DEFAULT 0,
            last_seen REAL,
            last_ip TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            note TEXT
        );
        
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS login_attempts (
            ip TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0,
            locked_until REAL NOT NULL DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            ip TEXT,
            username TEXT,
            action TEXT NOT NULL,
            detail TEXT,
            success INTEGER NOT NULL
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_uid ON users(uid);
        CREATE INDEX IF NOT EXISTS idx_users_enabled ON users(enabled);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
    """)
    await db.commit()


@asynccontextmanager
async def get_db():
    db = await _ensure_db()
    try:
        yield db
    finally:
        await db.close()


async def log_audit(
    action: str,
    ip: Optional[str] = None,
    username: Optional[str] = None,
    detail: Optional[str] = None,
    success: bool = True,
):
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO audit_log (ts, ip, username, action, detail, success) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), ip, username, action, detail, int(success)),
            )
            await db.commit()
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")


async def get_setting(key: str, default: Any = None) -> Any:
    async with get_db() as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return default
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return default


async def set_setting(key: str, value: Any):
    async with get_db() as db:
        await db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value), time.time()),
        )
        await db.commit()


async def is_setup_complete() -> bool:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM admin") as cursor:
            row = await cursor.fetchone()
            return row[0] > 0
