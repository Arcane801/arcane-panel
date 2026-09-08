"""
Arcane Panel — Centralized Configuration
All secrets and tunables come from environment variables.
No defaults that weaken security.
"""
import os
import secrets


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


# --- Core ---
APP_VERSION = "0.1.0"
APP_NAME = "Arcane Panel"
DEBUG = _env_bool("DEBUG", False)

# --- Network ---
PORT = _env_int("PORT", 8080)
APP_PORT = _env_int("APP_PORT", 10000)
XRAY_API_PORT = _env_int("XRAY_API_PORT", 10001)

# --- Security ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY and not DEBUG:
    raise RuntimeError(
        "SECRET_KEY environment variable is required in production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)

SESSION_COOKIE = "arcane_session"
SESSION_MAX_AGE = _env_int("SESSION_MAX_AGE", 8 * 3600)

# --- Password Policy ---
MIN_PASSWORD_LEN = 12
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = True
SPECIAL_CHARS = r"!@#$%^&*()-_=+[]{}|;:,.<>?"

# --- Rate Limiting ---
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
API_RATE_LIMIT_PER_MINUTE = 60

# --- Xray ---
XRAY_BINARY_PATH = "/usr/local/bin/xray"
XRAY_CONFIG_PATH = os.getenv("XRAY_CONFIG_PATH", "/app/data/xray_config.json")

# --- Storage ---
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "arcane.db")
