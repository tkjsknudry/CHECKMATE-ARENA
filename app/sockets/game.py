"""Handler Socket.IO: permainan realtime, chat, dan matchmaking."""

import re
import threading
import time
from collections import defaultdict, deque

from flask import request, session
from flask_socketio import emit, join_room

from app.database import get_db
from app.extensions import socketio
from app.services import game_service as gs

_sid_info = {}  # sid -> {"code": ..., "color": ...}
_queue = {}  # user_id -> {"sid": ..., "rating": ..., "since": ...}
_queue_lock = threading.Lock()
_chat_times = defaultdict(lambda: deque(maxlen=5))
_loop_started = False

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


# ===== Util =====

def _error(message):
    emit("error_message", {"message": message})


def _current_user(db):
    user_id = session.get("user_id")
    if user_id is None:
        return None
    row = db.execute("SELECT id, username, rating FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def _member_game(db, data):
    """Kembalikan (user, game, warna, error). Hanya anggota room yang lolos."""
    if not isinstance(data, dict):
        return None, None, None, "Data tidak valid."
    user = _current_user(db)
    if user is None:
        return None, None, None, "Sesi tidak valid. Muat ulang halaman."
    code = str(data.get("code", "")).strip().upper()[:8]
    game = gs.get_game(db, code)
    if game is None:
        return None, None, None, "Room tidak ditemukan."
    color = game.color_of(user["id"])
    if color is None:
        return None, None, None, "Kamu bukan pemain di room ini."
    return user, game, color, None


def _broadcast(game):
    with game.lock:
        state = game.to_state()
    socketio.emit("game_state", state, to=game.code)


def _run_action(data, action):
    db = get_db()
    user, game, _color, error = _member_game(db, data)
    if error:
        _error(error)
        return
    ok, message = action(db, game, user["id"], data)
    if not ok and message:
        _error(message)
    _broadcast(game)


# ===== Permainan =====

@socketio.on("join_game")
def on_join_game(data):
    db = get_db()
    user, game, color, error = _member_game(db, data)
    if error:
        _error(error)
        return

    with game.lock:
        game.sids[color].add(request.sid)
        game.reset_presence()
        game.start_clock_if_ready()

    _sid_info[request.sid] = {"code": game.code, "color": color}
    join_room(game.code)
    _broadcast(game)
    emit("chat_history", gs.get_chat_history(db, game.id))


@socketio.on("make_move")
def on_make_move(data):
    db = get_db()
    user, game, _color, error = _member_game(db, data)
    if error:
        _error(error)
        return
    ok, message = gs.apply_move(
        db, game, user["id"], data.get("from"), data.get("to"), data.get("promotion")
    )
    if not ok:
        emit("move_rejected", {"message": message})
    _broadcast(game)


@socketio.on("resign")
def on_resign(data):
    _run_action(data, lambda db, game, uid, _d: gs.resign(db, game, uid))


@socketio.on("offer_draw")
def on_offer_draw(data):
    _run_action(data, lambda db, game, uid, _d: gs.offer_draw(db, game, uid))


@socketio.on("respond_draw")
def on_respond_draw(data):
    _run_action(
        data, lambda db, game, uid, d: gs.respond_draw(db, game, uid, bool(d.get("accept")))
    )


@socketio.on("chat_send")
def on_chat_send(data):
    db = get_db()
    user, game, _color, error = _member_game(db, data)
    if error:
        _error(error)
        return

    body = CONTROL_CHARS.sub("", str(data.get("text", "")))
    body = " ".join(body.split())
    if not body:
        return
    if len(body) > 200:
        _error("Pesan maksimal 200 karakter.")
        return

    now = time.time()
    times = _chat_times[user["id"]]
    if times and now - times[-1] < 0.8:
        _error("Terlalu cepat. Tunggu sebentar.")
        return
    if len(times) == times.maxlen and now - times[0] < 10:
        _error("Pelan-pelan, jangan spam.")
        return
    times.append(now)

    message = gs.save_chat(db, game, user["id"], user["username"], body)
    socketio.emit("chat_message", message, to=game.code)


@socketio.on("disconnect")
def on_disconnect(*_args):
    sid = request.sid
    with _queue_lock:
        for uid, entry in list(_queue.items()):
            if entry["sid"] == sid:
                del _queue[uid]

    info = _sid_info.pop(sid, None)
    if not info:
        return
    game = gs.peek_game(info["code"])
    if game is None:
        return
    with game.lock:
        game.sids[info["color"]].discard(sid)
        game.reset_presence()
    _broadcast(game)


# ===== Matchmaking =====

@socketio.on("queue_join")
def on_queue_join(*_args):
    db = get_db()
    user = _current_user(db)
    if user is None:
        _error("Sesi tidak valid. Muat ulang halaman.")
        return

    open_game = gs.find_open_game(db, user["id"])
    if open_game and open_game["status"] == "active":
        emit("match_found", {"code": open_game["room_code"]})
        return

    with _queue_lock:
        _queue[user["id"]] = {"sid": request.sid, "rating": user["rating"], "since": time.time()}
    emit("queue_status", {"state": "searching"})
    _try_match(db)


@socketio.on("queue_leave")
def on_queue_leave(*_args):
    user_id = session.get("user_id")
    with _queue_lock:
        entry = _queue.get(user_id)
        if entry and entry["sid"] == request.sid:
            del _queue[user_id]


def _try_match(db):
    """Pasangkan pemain di antrean. Selisih rating yang diizinkan melebar seiring waktu."""
    matches = []
    with _queue_lock:
        now = time.time()
        entries = sorted(_queue.items(), key=lambda item: item[1]["since"])
        used = set()
        for uid, entry in entries:
            if uid in used:
                continue
            best, best_diff = None, None
            for other_id, other in entries:
                if other_id == uid or other_id in used:
                    continue
                diff = abs(entry["rating"] - other["rating"])
                window = 150 + 25 * max(now - entry["since"], now - other["since"])
                if diff <= window and (best is None or diff < best_diff):
                    best, best_diff = other_id, diff
            if best is not None:
                used.update((uid, best))
                matches.append((uid, entry, best, _queue[best]))
        for uid, _entry, other_id, _other in matches:
            _queue.pop(uid, None)
            _queue.pop(other_id, None)

    for uid, entry, other_id, other in matches:
        try:
            code = gs.create_match(db, uid, other_id)
        except Exception:  # noqa: BLE001
            for sid in (entry["sid"], other["sid"]):
                socketio.emit(
                    "error_message", {"message": "Gagal membuat pertandingan. Coba lagi."}, to=sid
                )
            continue
        socketio.emit("match_found", {"code": code}, to=entry["sid"])
        socketio.emit("match_found", {"code": code}, to=other["sid"])


# ===== Loop latar belakang (jam, disconnect, matchmaking) =====

def start_background_loop(app):
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    socketio.start_background_task(_loop, app)


def _loop(app):
    while True:
        socketio.sleep(1)
        try:
            with app.app_context():
                db = get_db()
                for game in gs.check_timeouts(db):
                    _broadcast(game)
                _try_match(db)
                gs.cleanup_cache()
        except Exception:  # noqa: BLE001
            app.logger.exception("Kesalahan pada loop latar belakang")