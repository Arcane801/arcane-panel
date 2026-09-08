"""
Arcane Panel — Security Middleware
Rate limiting, security headers, request sanitization.
"""
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(list)
    
    def is_allowed(self, key: str) -> tuple:
        now = time.time()
        cutoff = now - self.window_seconds
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        if len(self._hits[key]) >= self.max_requests:
            retry_after = int(self._hits[key][0] - cutoff) + 1
            return False, retry_after
        self._hits[key].append(now)
        return True, 0


api_limiter = RateLimiter(max_requests=60, window_seconds=60)
login_limiter = RateLimiter(max_requests=10, window_seconds=60)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "frame-ancestors 'none';"
        )
        
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from .auth import get_client_ip
        ip = get_client_ip(request)
        path = request.url.path
        
        if path == "/api/login":
            allowed, retry_after = login_limiter.is_allowed(ip)
            if not allowed:
                return JSONResponse(
                    {"error": "rate-limited", "retry_after": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
        elif path.startswith("/api/") and path != "/health":
            allowed, retry_after = api_limiter.is_allowed(ip)
            if not allowed:
                return JSONResponse(
                    {"error": "rate-limited", "retry_after": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
        
        return await call_next(request)
