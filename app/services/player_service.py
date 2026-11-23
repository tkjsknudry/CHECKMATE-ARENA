"""Layanan profil pemain: validasi nickname dan pembuatan profil."""

import re
import sqlite3

NICKNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")

RESERVED_NAMES = {
    "admin", "administrator", "moderator", "system", "server",
    "checkmate", "arena", "guest", "tamu", "support", "staff",
}

AVATAR_COLORS = ["#d9b44a", "#8aa2ff", "#c58bff", "#5fd0c0", "#ff9d7a", "#7fc8f8"]


class NicknameTakenError(Exception):
    """Nickname sudah dipakai pemain lain."""


def validate_nickname(raw: str):
    """Kembalikan (nickname_bersih, pesan_error). Salah satunya selalu None."""
    nickname = (raw or "").strip()

    if len(nickname) < 3 or len(nickname) > 20:
        return None, "Nickname harus 3 sampai 20 karakter."
    if not NICKNAME_RE.match(nickname):
        return None, "Nickname hanya boleh berisi huruf, angka, dan garis bawah (_)."
    if nickname.lower() in RESERVED_NAMES:
        return None, "Nickname ini tidak bisa dipakai. Coba yang lain."
    return nickname, None


def create_player(db, nickname: str) -> dict:
    """Buat profil baru (rating awal 1200). Lempar NicknameTakenError jika sudah dipakai."""
    color = AVATAR_COLORS[sum(ord(ch) for ch in nickname.lower()) % len(AVATAR_COLORS)]

    try:
        with db:  # transaksi: otomatis commit, atau rollback jika error
            cursor = db.execute(
                "INSERT INTO users (username, avatar_color) VALUES (?, ?)",
                (nickname, color),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise NicknameTakenError(nickname) from None

    return dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())