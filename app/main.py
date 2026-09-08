"""
Arcane Panel — Main Application
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config
from .storage import get_db, log_audit, is_setup_complete
from .auth import (
    verify_admin_credentials, record_login_attempt, check_login_lock,
    set_session_cookie, clear_session_cookie, require_auth,
    validate_password, hash_password, get_client_ip,
)
from .security import SecurityHeadersMiddleware, RateLimitMiddleware
from .users import list_users, create_user, update_user, delete_user, rotate_uuid, get_user
from .xray import xray_manager
from .settings import get_all_settings, update_settings
from .subscription import router as subscription_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    from .storage import _ensure_db
    await _ensure_db()
    try:
        await xray_manager.start()
    except Exception as e:
        print(f"[ERROR] Failed to start Xray: {e}")
    await log_audit(action="app.startup", detail=f"version={config.APP_VERSION}")
    yield
    await xray_manager.stop()
    await log_audit(action="app.shutdown")


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

if os.path.isdir("/app/static"):
    app.mount("/static", StaticFiles(directory="/app/static"), name="static")

templates = Jinja2Templates(directory="/app/app/templates")

app.include_router(subscription_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": config.APP_VERSION}


@app.get("/setup")
async def setup_page(request: Request):
    if await is_setup_complete():
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("setup.html", {"request": request})


@app.post("/api/setup")
async def api_setup(request: Request):
    if await is_setup_complete():
        raise HTTPException(400, "already-configured")
    payload = await request.json()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    ip = get_client_ip(request)
    import re
    if not re.match(r"^[a-zA-Z0-9_]{3,32}$", username):
        raise HTTPException(400, "invalid-username: 3-32 alphanumeric/underscore")
    valid, err = validate_password(password)
    if not valid:
        raise HTTPException(400, err)
    hp = hash_password(password)
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM admin") as cursor:
            if (await cursor.fetchone())[0] > 0:
                raise HTTPException(400, "already-configured")
        await db.execute(
            "INSERT INTO admin (id, username, password_hash, salt, created_at) "
            "VALUES (1, ?, ?, ?, ?)",
            (username, hp["hash"], hp["salt"], __import__("time").time()),
        )
        await db.commit()
    await log_audit(action="admin.setup", ip=ip, username=username, success=True)
    resp = JSONResponse({"ok": True})
    set_session_cookie(resp, request, username, hp["hash"][:12])
    return resp


@app.post("/api/login")
async def api_login(request: Request):
    payload = await request.json()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    ip = get_client_ip(request)
    remaining = await check_login_lock(ip)
    if remaining:
        await log_audit(action="login.locked", ip=ip, username=username, success=False)
        raise HTTPException(429, f"locked:{remaining}")
    admin = await verify_admin_credentials(username, password)
    if not admin:
        await record_login_attempt(ip, success=False)
        await log_audit(action="login.failed", ip=ip, username=username, success=False)
        raise HTTPException(401, "invalid-credentials")
    await record_login_attempt(ip, success=True)
    await log_audit(action="login.success", ip=ip, username=username, success=True)
    resp = JSONResponse({"ok": True})
    set_session_cookie(resp, request, username, admin["password_hash"][:12])
    return resp


@app.post("/api/logout")
async def api_logout(request: Request, user: str = Depends(require_auth)):
    await log_audit(action="logout", ip=get_client_ip(request), username=user)
    resp = JSONResponse({"ok": True})
    clear_session_cookie(resp)
    return resp


@app.get("/api/users")
async def api_list_users(user: str = Depends(require_auth)):
    return {"users": await list_users()}


@app.post("/api/users")
async def api_create_user(request: Request, user: str = Depends(require_auth)):
    payload = await request.json()
    name = (payload.get("name") or "").strip()
    if not name or len(name) > 64:
        raise HTTPException(400, "invalid-name")
    u = await create_user(
        name=name,
        max_gb=payload.get("max_gb"),
        expires_at=payload.get("expires_at"),
        max_requests=payload.get("max_requests"),
        max_connections=payload.get("max_connections"),
        ip_lock=payload.get("ip_lock"),
        note=payload.get("note"),
        created_by=user,
        ip=get_client_ip(request),
    )
    return {"user": u}


@app.put("/api/users/{uid}")
async def api_update_user(uid: str, request: Request, user: str = Depends(require_auth)):
    payload = await request.json()
    ok = await update_user(uid, payload, updated_by=user, ip=get_client_ip(request))
    if not ok:
        raise HTTPException(404, "user-not-found")
    return {"ok": True}


@app.delete("/api/users/{uid}")
async def api_delete_user(uid: str, request: Request, user: str = Depends(require_auth)):
    ok = await delete_user(uid, deleted_by=user, ip=get_client_ip(request))
    if not ok:
        raise HTTPException(404, "user-not-found")
    return {"ok": True}


@app.post("/api/users/{uid}/rotate")
async def api_rotate_uuid(uid: str, request: Request, user: str = Depends(require_auth)):
    new_uuid = await rotate_uuid(uid, rotated_by=user, ip=get_client_ip(request))
    if not new_uuid:
        raise HTTPException(404, "user-not-found")
    return {"ok": True, "uuid": new_uuid}


@app.get("/api/settings")
async def api_get_settings(user: str = Depends(require_auth)):
    settings = await get_all_settings()
    return {"settings": settings}


@app.put("/api/settings")
async def api_update_settings(request: Request, user: str = Depends(require_auth)):
    payload = await request.json()
    ip = get_client_ip(request)
    try:
        ok = await update_settings(payload, updated_by=user, ip=ip)
        if not ok:
            raise HTTPException(400, "no-valid-settings")
        await xray_manager.reload()
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/stats")
async def api_get_stats(user: str = Depends(require_auth)):
    stats = await xray_manager.get_stats()
    return {"stats": stats}


@app.post("/api/xray/reload")
async def api_xray_reload(user: str = Depends(require_auth)):
    await xray_manager.reload()
    return {"ok": True}


@app.get("/api/xray/status")
async def api_xray_status(user: str = Depends(require_auth)):
    if xray_manager.process and xray_manager.process.returncode is None:
        return {"status": "running", "pid": xray_manager.process.pid}
    return {"status": "stopped", "pid": None}


@app.get("/")
async def index(request: Request):
    if not await is_setup_complete():
        return RedirectResponse("/setup", status_code=302)
    return templates.TemplateResponse("index.html", {"request": request, "version": config.APP_VERSION})


@app.get("/login")
async def login_page(request: Request):
    if not await is_setup_complete():
        return RedirectResponse("/setup", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"[ERROR] {request.method} {request.url.path}: {exc}")
    return JSONResponse({"error": "internal-error"}, status_code=500)
