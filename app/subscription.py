"""
Arcane Panel — Subscription Endpoints
"""
import base64
import time
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from .users import get_user, list_users
from .settings import get_all_settings, get_domain
from .config_generator import generate_vless_link, generate_subscription

router = APIRouter()

@router.get("/sub/{uid}")
async def subscription(uid: str, request: Request):
    user = await get_user(uid)
    if not user or not user["enabled"]:
        raise HTTPException(404, "not-found")
    if user.get("expires_at") and user["expires_at"] < time.time():
        raise HTTPException(403, "expired")
    if user.get("max_gb"):
        used = (user.get("used_bytes_up", 0) + user.get("used_bytes_down", 0)) / (1024**3)
        if used >= user["max_gb"]:
            raise HTTPException(403, "traffic-limit-exceeded")
    
    settings = await get_all_settings()
    domain = await get_domain(request.headers.get("host", "localhost"))
    
    # Generate single VLESS link (not base64 for v2rayNG)
    link = generate_vless_link(user, domain, 443, settings)
    
    return Response(
        content=link,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{uid}.txt"',
            "Profile-Update-Interval": "12",
        },
    )

@router.get("/sub/plain/{uid}")
async def subscription_plain(uid: str, request: Request):
    user = await get_user(uid)
    if not user or not user["enabled"]:
        raise HTTPException(404, "not-found")
    settings = await get_all_settings()
    domain = await get_domain(request.headers.get("host", "localhost"))
    link = generate_vless_link(user, domain, 443, settings)
    return Response(content=link, media_type="text/plain")
