# 🔒 Security Policy — Arcane Panel

## Security Principles

### ✅ What we DO
- Pin Xray binary version with SHA-256 verification
- PBKDF2-SHA256 with 600k iterations for password hashing
- Strong password policy (12+ chars, mixed case, digits, special)
- HttpOnly + SameSite=Strict + Secure cookies
- CSP, HSTS, X-Frame-Options headers
- Rate limit login attempts (5 attempts → 15 min lock)
- Comprehensive audit logging
- Non-root container execution
- Require SECRET_KEY in production

### 🚫 What we DON'T do
- ❌ No OTA / self-update
- ❌ No telemetry
- ❌ No eval/exec on user input
- ❌ No hardcoded secrets
- ❌ No Swagger/OpenAPI in production
- ❌ No backdoors

## Reporting a Vulnerability

Email: security@your-domain.com
We respond within 48 hours.
