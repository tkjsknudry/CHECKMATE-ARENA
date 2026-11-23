"""Konfigurasi utama CHECKMATE ARENA."""

import os
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def _load_secret_key() -> str:
    """Ambil SECRET_KEY dari environment, atau buat otomatis dan simpan di instance/."""
    env_key = os.environ.get("CHECKMATE_SECRET_KEY")
    if env_key:
        return env_key

    INSTANCE_DIR.mkdir(exist_ok=True)
    key_file = INSTANCE_DIR / "secret_key.txt"

    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()

    new_key = secrets.token_hex(32)
    key_file.write_text(new_key, encoding="utf-8")
    return new_key


class Config:
    APP_NAME = "CHECKMATE ARENA"

    SECRET_KEY = _load_secret_key()
    DATABASE_PATH = str(INSTANCE_DIR / "checkmate.db")

    # Keamanan session / cookie
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # ubah ke True saat memakai HTTPS (deployment)
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)

    # Server
    HOST = "0.0.0.0"
    PORT = 5000
    SOCKETIO_ASYNC_MODE = "threading"