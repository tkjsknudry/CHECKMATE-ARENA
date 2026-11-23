"""Utilitas session: pemain saat ini, proteksi halaman, dan token CSRF."""

import hmac
import secrets
from functools import wraps

from flask import g, redirect, request, session, url_for

from app.database import get_db


def get_current_player():
    """Kembalikan data pemain dari session (dict), atau None jika belum punya profil."""
    user_id = session.get("user_id")
    if user_id is None:
        return None

    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        # Profil sudah tidak ada di database (misalnya database di-reset)
        session.pop("user_id", None)
        return None
    return dict(row)


def login_required(view):
    """Halaman hanya untuk pemain yang sudah punya profil."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        player = get_current_player()
        if player is None:
            if request.method == "GET" and request.path.startswith("/game/"):
                session["next"] = request.path
            return redirect(url_for("auth.welcome"))
        g.player = player
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def verify_csrf() -> bool:
    sent = request.form.get("csrf_token", "")
    expected = session.get("_csrf", "")
    return bool(expected) and hmac.compare_digest(sent, expected)