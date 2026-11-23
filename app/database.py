"""Modul koneksi dan inisialisasi database SQLite."""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _connect(db_path: str) -> sqlite3.Connection:
    """Buat koneksi baru dengan pengaturan aman."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def get_db() -> sqlite3.Connection:
    """Koneksi database untuk satu request/app context (dipakai ulang)."""
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE_PATH"])
    return g.db


def open_connection() -> sqlite3.Connection:
    """Koneksi baru yang ditutup sendiri oleh pemanggil (untuk service/socket)."""
    return _connect(current_app.config["DATABASE_PATH"])


def close_db(error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """Buat semua tabel jika belum ada."""
    db_path = app.config["DATABASE_PATH"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    try:
        # WAL: pembacaan dan penulisan bisa berjalan bersamaan (cocok untuk multiplayer)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8-sig"))
        conn.commit()
    finally:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    init_db(app)