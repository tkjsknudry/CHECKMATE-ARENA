"""Route nickname: halaman sambutan, pembuatan profil, dan keluar."""

import time
from collections import defaultdict

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.database import get_db
from app.services.player_service import (
    NicknameTakenError,
    create_player,
    validate_nickname,
)
from app.utils.auth import get_current_player, verify_csrf

auth_bp = Blueprint("auth", __name__)

# Pembatasan sederhana: maksimal 5 profil baru per 10 menit untuk tiap alamat IP.
_CREATE_LIMIT = 5
_CREATE_WINDOW = 600
_recent_creations = defaultdict(list)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _recent_creations[ip] if now - t < _CREATE_WINDOW]
    _recent_creations[ip] = attempts
    return len(attempts) >= _CREATE_LIMIT


@auth_bp.route("/welcome")
def welcome():
    if get_current_player():
        return redirect(url_for("dashboard.index"))
    return render_template("auth/welcome.html", error=None, nickname="")


@auth_bp.route("/join", methods=["POST"])
def join():
    if not verify_csrf():
        abort(400)

    raw = request.form.get("nickname", "")
    nickname, error = validate_nickname(raw)
    status = 400

    ip = request.remote_addr or "unknown"
    if error is None and _rate_limited(ip):
        error = "Terlalu banyak percobaan. Tunggu beberapa menit lalu coba lagi."
        status = 429

    if error is None:
        try:
            player = create_player(get_db(), nickname)
        except NicknameTakenError:
            error = "Nickname itu sudah dipakai pemain lain. Coba yang lain."
            status = 409
        else:
            _recent_creations[ip].append(time.time())
            next_path = session.get("next", "")
            session.clear()
            session["user_id"] = player["id"]
            session.permanent = True
            if next_path.startswith("/game/") and "//" not in next_path:
                return redirect(next_path)
            return redirect(url_for("dashboard.index"))

    return render_template("auth/welcome.html", error=error, nickname=raw[:20]), status


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if not verify_csrf():
        abort(400)
    session.clear()
    return redirect(url_for("auth.welcome"))