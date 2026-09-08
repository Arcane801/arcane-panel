"""
Arcane Panel — Xray Core Manager
"""
import asyncio
import json
import os
import signal
import time
from typing import Optional, Dict, List, Any

from . import config
from .storage import get_db, log_audit


class XrayManager:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config_path = config.XRAY_CONFIG_PATH
        self._stats_cache: Dict[str, Dict[str, Any]] = {}
        self._last_stats_fetch = 0.0
    
    async def start(self):
        if self.process and self.process.returncode is None:
            return
        if not os.path.exists(config.XRAY_BINARY_PATH):
            await log_audit(action="xray.binary_missing", success=False)
            return
        if not os.path.exists(self.config_path):
            await self.generate_config()
        self.process = await asyncio.create_subprocess_exec(
            config.XRAY_BINARY_PATH, "run", "-c", self.config_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await log_audit(action="xray.start", detail=f"pid={self.process.pid}")
        asyncio.create_task(self._monitor_process())
    
    async def _monitor_process(self):
        if not self.process:
            return
        await self.process.wait()
        exit_code = self.process.returncode
        if exit_code != 0:
            stderr_data = await self.process.stderr.read()
            await log_audit(
                action="xray.crash",
                detail=f"exit_code={exit_code} stderr={stderr_data.decode()[:500]}",
                success=False,
            )
            await asyncio.sleep(5)
            await self.start()
    
    async def stop(self):
        if not self.process or self.process.returncode is not None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.process.kill()
        await log_audit(action="xray.stop")
    
    async def reload(self):
        if not self.process or self.process.returncode is not None:
            await self.start()
            return
        await self.generate_config()
        try:
            self.process.send_signal(signal.SIGHUP)
        except (ProcessLookupError, AttributeError):
            await self.start()
            return
        await log_audit(action="xray.reload")
        await asyncio.sleep(1)
    
    async def generate_config(self):
        async with get_db() as db:
            async with db.execute("SELECT * FROM users WHERE enabled = 1") as cursor:
                users = [dict(row) for row in await cursor.fetchall()]
            async with db.execute("SELECT key, value FROM settings") as cursor:
                settings = {row[0]: json.loads(row[1]) for row in await cursor.fetchall()}
        xray_config = self._build_config(users, settings)
        tmp_path = f"{self.config_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(xray_config, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)
    
    def _build_config(self, users: List[Dict], settings: Dict) -> Dict:
        transport = settings.get("transport", "ws")
        vless_inbound = {
            "listen": "127.0.0.1",
            "port": config.APP_PORT + 1,
            "protocol": "vless",
            "settings": {
                "clients": [{"id": u["uuid"], "email": u["uid"]} for u in users],
                "decryption": "none",
            },
            "streamSettings": {
                "network": transport,
                "security": "none",
            },
            "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            "tag": "vless-in",
        }
        if transport == "ws":
            vless_inbound["streamSettings"]["wsSettings"] = {
                "path": "/vl-ws",
                "headers": {"Host": settings.get("sni_override") or ""},
            }
        elif transport == "xhttp":
            vless_inbound["streamSettings"]["xhttpSettings"] = {
                "path": "/vl-xhttp",
                "mode": "packet-up",
            }
        api_inbound = {
            "listen": "127.0.0.1",
            "port": config.XRAY_API_PORT,
            "protocol": "dokodemo-door",
            "settings": {"address": "127.0.0.1"},
            "tag": "api",
        }
        return {
            "log": {"loglevel": "warning"},
            "inbounds": [vless_inbound, api_inbound],
            "outbounds": [{"protocol": "freedom", "tag": "direct"}],
            "routing": {
                "rules": [
                    {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
                ],
            },
            "stats": {},
            "api": {"tag": "api", "services": ["StatsService"]},
            "policy": {
                "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
                "system": {"statsInboundUplink": False, "statsInboundDownlink": False},
            },
        }
    
    async def get_stats(self, force_refresh: bool = False) -> Dict[str, Dict[str, int]]:
        now = time.time()
        if not force_refresh and (now - self._last_stats_fetch) < 5:
            return self._stats_cache
        self._last_stats_fetch = now
        return self._stats_cache


xray_manager = XrayManager()
