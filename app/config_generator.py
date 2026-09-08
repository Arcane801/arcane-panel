"""
Arcane Panel — VLESS Config Generator
"""
import base64
import time
import urllib.parse
from typing import Dict, List, Optional


def generate_vless_link(
    user: Dict,
    domain: str,
    port: int = 443,
    settings: Optional[Dict] = None,
) -> str:
    settings = settings or {}
    params = {
        "type": settings.get("transport", "ws"),
        "security": "tls",
        "sni": settings.get("sni_override") or domain,
        "fp": settings.get("fingerprint", "chrome"),
        "alpn": settings.get("alpn", "http/1.1"),
    }
    transport = params["type"]
    if transport == "ws":
        params["path"] = "/vl-ws"
        params["host"] = settings.get("sni_override") or domain
    elif transport == "xhttp":
        params["path"] = "/vl-xhttp"
        params["mode"] = "packet-up"
    if settings.get("fragment_enabled"):
        frag_length = settings.get("fragment_length", "10-30")
        frag_interval = settings.get("fragment_interval", "10-20")
        frag_packets = settings.get("fragment_packets", "tlshello")
        params["fragment"] = f"{frag_length},{frag_packets},{frag_interval}"
    query = urllib.parse.urlencode(params)
    name = urllib.parse.quote(user["name"])
    return f"vless://{user['uuid']}@{domain}:{port}?{query}#{name}"


def generate_subscription(users: List[Dict], domain: str, settings: Dict) -> str:
    lines = []
    for user in users:
        if not user.get("enabled"):
            continue
        if user.get("expires_at") and user["expires_at"] < time.time():
            continue
        if user.get("max_gb"):
            used_gb = (user.get("used_bytes_up", 0) + user.get("used_bytes_down", 0)) / (1024**3)
            if used_gb >= user["max_gb"]:
                continue
        link = generate_vless_link(user, domain, 443, settings)
        lines.append(link)
    content = "\n".join(lines)
    return base64.b64encode(content.encode("utf-8")).decode("utf-8")
