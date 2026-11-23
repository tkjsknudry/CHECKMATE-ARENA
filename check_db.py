"""Pemeriksaan database CHECKMATE ARENA. Semua data uji dibatalkan (rollback)."""

import sqlite3

from app import create_app
from app.database import get_db

app = create_app()

with app.app_context():
    db = get_db()

    tables = [
        r["name"]
        for r in db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    user_columns = [r["name"] for r in db.execute("PRAGMA table_info(users)")]

    print("Tabel          :", ", ".join(tables))
    print("Kolom users    :", ", ".join(user_columns))
    print("Password?      :", "ADA (salah)" if "password_hash" in user_columns else "tidak ada (benar)")
    print("Foreign keys   :", db.execute("PRAGMA foreign_keys").fetchone()[0], "(harus 1)")
    print("Journal mode   :", db.execute("PRAGMA journal_mode").fetchone()[0], "(harus wal)")
    print("Integrity check:", db.execute("PRAGMA integrity_check").fetchone()[0], "(harus ok)")
    print("Jumlah user    :", db.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    print("-" * 45)

    def expect_error(label, sql, params=()):
        try:
            db.execute(sql, params)
            print(f"GAGAL  {label}: seharusnya ditolak tapi diterima")
        except sqlite3.IntegrityError:
            print(f"OK     {label}: ditolak database")

    # Data uji (semuanya akan di-rollback)
    db.execute("INSERT INTO users (username) VALUES ('Budi')")
    db.execute("INSERT INTO games (room_code, white_id) VALUES ('TEST01', 1)")
    game_id = db.execute("SELECT id FROM games WHERE room_code = 'TEST01'").fetchone()[0]
    db.execute(
        "INSERT INTO moves (game_id, ply, san, uci, fen_after) VALUES (?, 1, 'e4', 'e2e4', 'f')",
        (game_id,),
    )

    expect_error("nickname kembar beda huruf besar", "INSERT INTO users (username) VALUES ('budi')")
    expect_error("nickname terlalu pendek", "INSERT INTO users (username) VALUES ('ab')")
    expect_error("langkah ganda di ply yang sama", "INSERT INTO moves (game_id, ply, san, uci, fen_after) VALUES (?, 1, 'd4', 'd2d4', 'f')", (game_id,))
    expect_error("game dengan pemain tidak ada", "INSERT INTO games (room_code, white_id) VALUES ('TEST02', 9999)")
    expect_error("chat kosong", "INSERT INTO messages (game_id, user_id, body) VALUES (?, 1, '')", (game_id,))

    db.rollback()
    print("-" * 45)
    print("User setelah rollback:", db.execute("SELECT COUNT(*) FROM users").fetchone()[0], "(harus 0)")