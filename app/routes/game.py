"""Route room dan halaman permainan."""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from app.database import get_db
from app.services import game_service as gs
from app.utils.auth import login_required, verify_csrf
from app.utils.network import get_local_ip

game_bp = Blueprint("game", __name__)


@game_bp.route("/room/create", methods=["POST"])
@login_required
def create_room():
    if not verify_csrf():
        abort(400)
    code, _resumed = gs.create_room(
        get_db(),
        g.player["id"],
        request.form.get("time_control", ""),
        request.form.get("color", ""),
    )
    return redirect(url_for("game.play", code=code))


@game_bp.route("/room/join", methods=["POST"])
@login_required
def join_room_view():
    if not verify_csrf():
        abort(400)
    code, error = gs.join_room(get_db(), g.player["id"], request.form.get("code", ""))
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("game.play", code=code))


@game_bp.route("/game/<code>")
@login_required
def play(code):
    db = get_db()
    code = code.strip().upper()[:8]
    player = g.player

    game = gs.get_game(db, code)
    if game is None:
        flash("Room tidak ditemukan.", "error")
        return redirect(url_for("dashboard.index"))

    color = game.color_of(player["id"])
    if color is None:
        # Membuka link undangan: otomatis bergabung jika masih ada kursi kosong
        _code, error = gs.join_room(db, player["id"], code)
        if error:
            flash(error, "error")
            return redirect(url_for("dashboard.index"))
        game = gs.get_game(db, code)
        color = game.color_of(player["id"])
        if color is None:
            return redirect(url_for("dashboard.index"))

    host = request.host
    if host.startswith(("127.", "localhost")):
        host = f"{get_local_ip()}:{current_app.config['PORT']}"
    invite_url = f"{request.scheme}://{host}/game/{code}"

    return render_template(
        "game/play.html",
        code=code,
        game_config={"code": code, "myColor": color, "inviteUrl": invite_url},
    )