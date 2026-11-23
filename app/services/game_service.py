"""Layanan permainan.

State permainan hidup di memori server (sumber kebenaran) dan disimpan ke database
setiap ada perubahan penting. Browser tidak pernah dipercaya untuk status permainan.
"""

import random
import secrets
import sqlite3
import threading
import time

import chess

ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TIME_CONTROLS = {
    "180+0": (180, 0),
    "300+0": (300, 0),
    "600+0": (600, 0),
    "900+10": (900, 10),
}
DEFAULT_TC = "600+0"
DISCONNECT_LIMIT = 90  # detik: pemain terputus lebih lama dari ini dianggap kalah
NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
COLORS = ("white", "black")
START_COUNTS = {
    chess.QUEEN: 1,
    chess.ROOK: 2,
    chess.BISHOP: 2,
    chess.KNIGHT: 2,
    chess.PAWN: 8,
}

_games = {}
_games_lock = threading.RLock()


def opposite(color):
    return "black" if color == "white" else "white"


def captured_pieces(board):
    """Bidak yang sudah dimakan: {'white': [...yang dimakan putih], 'black': [...]}."""
    result = {"white": [], "black": []}
    for color in (chess.WHITE, chess.BLACK):
        missing = []
        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
            have = len(board.pieces(piece_type, color))
            missing += [chess.piece_symbol(piece_type)] * max(0, START_COUNTS[piece_type] - have)
        taken_by = "black" if color == chess.WHITE else "white"
        result[taken_by] = missing
    return result


class Game:
    def __init__(self, row):
        self.lock = threading.RLock()
        self.id = row["id"]
        self.code = row["room_code"]
        self.white_id = row["white_id"]
        self.black_id = row["black_id"]
        self.status = row["status"]
        self.base_ms = row["time_control_seconds"] * 1000
        self.inc_ms = row["increment_seconds"] * 1000

        self.board = chess.Board()
        self.sans = []
        self.last_move = None
        self.white_ms = self.base_ms
        self.black_ms = self.base_ms
        self.running = None  # 'white' / 'black' / None (jam belum jalan)
        self.turn_started = 0.0
        self.draw_offer_by = None
        self.result = None

        self.players = {"white": None, "black": None}
        self.sids = {"white": set(), "black": set()}
        self.disconnected_at = {"white": None, "black": None}

    # ----- pemain -----
    def player_id(self, color):
        return self.white_id if color == "white" else self.black_id

    def color_of(self, user_id):
        if user_id is not None and user_id == self.white_id:
            return "white"
        if user_id is not None and user_id == self.black_id:
            return "black"
        return None

    def refresh_players(self, db):
        for color in COLORS:
            uid = self.player_id(color)
            if uid is None:
                self.players[color] = None
                continue
            row = db.execute(
                "SELECT id, username, rating, avatar_color FROM users WHERE id = ?", (uid,)
            ).fetchone()
            self.players[color] = dict(row) if row else None

    def apply_row(self, db, row):
        """Sinkronkan data keanggotaan/status dari database."""
        self.white_id = row["white_id"]
        self.black_id = row["black_id"]
        self.status = row["status"]
        self.refresh_players(db)
        self.reset_presence()

    def reset_presence(self):
        now = time.monotonic()
        for color in COLORS:
            if self.status != "active" or self.player_id(color) is None or self.sids[color]:
                self.disconnected_at[color] = None
            elif self.disconnected_at[color] is None:
                self.disconnected_at[color] = now

    # ----- jam -----
    def set_ms(self, color, value):
        if color == "white":
            self.white_ms = int(value)
        else:
            self.black_ms = int(value)

    def remaining(self, color):
        ms = self.white_ms if color == "white" else self.black_ms
        if self.running == color:
            ms -= (time.monotonic() - self.turn_started) * 1000
        return max(0, int(ms))

    def start_clock_if_ready(self):
        """Jam baru berjalan setelah kedua pemain terhubung."""
        if self.status != "active" or self.result is not None or self.running is not None:
            return
        if self.sids["white"] and self.sids["black"]:
            self.running = "white" if self.board.turn else "black"
            self.turn_started = time.monotonic()

    # ----- state untuk browser -----
    def to_state(self):
        board = self.board
        active = self.status == "active" and self.result is None

        legal = {}
        if active:
            for move in board.legal_moves:
                legal.setdefault(chess.square_name(move.from_square), set()).add(
                    chess.square_name(move.to_square)
                )

        check_square = chess.square_name(board.king(board.turn)) if board.is_check() else None

        players = {}
        for color in COLORS:
            info = self.players[color]
            players[color] = None if info is None else {**info, "connected": bool(self.sids[color])}

        return {
            "code": self.code,
            "status": self.status,
            "fen": board.fen(),
            "turn": "white" if board.turn else "black",
            "players": players,
            "moves": list(self.sans),
            "last_move": (
                {"from": self.last_move[0], "to": self.last_move[1]} if self.last_move else None
            ),
            "check": check_square,
            "legal": {k: sorted(v) for k, v in legal.items()},
            "clocks": {
                "white_ms": self.remaining("white"),
                "black_ms": self.remaining("black"),
                "running": self.running,
            },
            "draw_offer_by": self.draw_offer_by,
            "captured": captured_pieces(board),
            "time_control": {"base": self.base_ms // 1000, "inc": self.inc_ms // 1000},
            "result": self.result,
        }

    @classmethod
    def from_db(cls, db, row):
        game = cls(row)
        moves = db.execute(
            "SELECT uci, san, white_time_ms, black_time_ms FROM moves "
            "WHERE game_id = ? ORDER BY ply",
            (row["id"],),
        ).fetchall()
        for item in moves:
            game.board.push(chess.Move.from_uci(item["uci"]))
            game.sans.append(item["san"])
            game.last_move = (item["uci"][:2], item["uci"][2:4])
        if moves:
            last = moves[-1]
            if last["white_time_ms"] is not None:
                game.white_ms = last["white_time_ms"]
            if last["black_time_ms"] is not None:
                game.black_ms = last["black_time_ms"]

        game.refresh_players(db)

        if row["status"] == "finished" and row["result"]:
            before_w, before_b = row["white_rating_before"], row["black_rating_before"]
            after_w, after_b = row["white_rating_after"], row["black_rating_after"]
            game.result = {
                "winner": row["result"],
                "reason": row["result_reason"] or "",
                "rating_changes": {
                    "white": (after_w - before_w) if None not in (before_w, after_w) else 0,
                    "black": (after_b - before_b) if None not in (before_b, after_b) else 0,
                },
            }
        game.reset_presence()
        return game


# ===== Akses game =====

def get_game(db, code):
    code = (code or "").strip().upper()
    with _games_lock:
        row = db.execute("SELECT * FROM games WHERE room_code = ?", (code,)).fetchone()
        if row is None:
            return None
        game = _games.get(code)
        if game is None:
            game = Game.from_db(db, row)
            _games[code] = game
        elif game.status == "waiting" and row["status"] != "waiting":
            with game.lock:
                game.apply_row(db, row)
        return game


def peek_game(code):
    return _games.get(code)


def cleanup_cache():
    with _games_lock:
        for code, game in list(_games.items()):
            if game.status in ("finished", "abandoned") and not any(game.sids.values()):
                del _games[code]


# ===== Room =====

def generate_room_code(db):
    for _ in range(30):
        code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(6))
        if db.execute("SELECT 1 FROM games WHERE room_code = ?", (code,)).fetchone() is None:
            return code
    raise RuntimeError("Gagal membuat kode room unik.")


def find_open_game(db, user_id):
    row = db.execute(
        "SELECT room_code, status FROM games "
        "WHERE status IN ('waiting', 'active') AND (white_id = ? OR black_id = ?) "
        "ORDER BY (status = 'active') DESC, id DESC LIMIT 1",
        (user_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def _cancel_waiting_rooms(db, user_id):
    db.execute(
        "UPDATE games SET status = 'abandoned' "
        "WHERE status = 'waiting' AND (white_id = ? OR black_id = ?)",
        (user_id, user_id),
    )


def create_room(db, user_id, tc_key, color_choice):
    """Buat room baru. Jika pemain masih punya game aktif, kembalikan game itu."""
    open_game = find_open_game(db, user_id)
    if open_game and open_game["status"] == "active":
        return open_game["room_code"], True

    base, inc = TIME_CONTROLS.get(tc_key, TIME_CONTROLS[DEFAULT_TC])
    if color_choice not in COLORS:
        color_choice = random.choice(COLORS)

    code = generate_room_code(db)
    white_id = user_id if color_choice == "white" else None
    black_id = user_id if color_choice == "black" else None

    with db:
        _cancel_waiting_rooms(db, user_id)
        db.execute(
            "INSERT INTO games (room_code, white_id, black_id, time_control_seconds, "
            "increment_seconds) VALUES (?, ?, ?, ?, ?)",
            (code, white_id, black_id, base, inc),
        )
    return code, False


def join_room(db, user_id, code):
    """Gabung ke room. Mengembalikan (kode, None) atau (None, pesan_error)."""
    code = (code or "").strip().upper()
    row = db.execute("SELECT * FROM games WHERE room_code = ?", (code,)).fetchone()
    if row is None:
        return None, "Room tidak ditemukan. Periksa kembali kodenya."

    if user_id in (row["white_id"], row["black_id"]):
        return code, None

    if row["status"] != "waiting" or (row["white_id"] and row["black_id"]):
        return None, "Room ini sudah penuh atau sudah selesai."

    busy = db.execute(
        "SELECT 1 FROM games WHERE status = 'active' AND (white_id = ? OR black_id = ?) LIMIT 1",
        (user_id, user_id),
    ).fetchone()
    if busy:
        return None, "Selesaikan pertandingan yang sedang berjalan dulu."

    slot = "white_id" if row["white_id"] is None else "black_id"
    with db:
        _cancel_waiting_rooms(db, user_id)
        cursor = db.execute(
            f"UPDATE games SET {slot} = ?, status = 'active', started_at = {NOW_SQL} "
            f"WHERE room_code = ? AND status = 'waiting' AND {slot} IS NULL",
            (user_id, code),
        )
        if cursor.rowcount == 0:
            return None, "Room ini sudah penuh."
        db.execute(
            "UPDATE games SET "
            "white_rating_before = (SELECT rating FROM users WHERE id = games.white_id), "
            "black_rating_before = (SELECT rating FROM users WHERE id = games.black_id) "
            "WHERE room_code = ?",
            (code,),
        )
    return code, None


def create_match(db, user_a, user_b, tc_key=DEFAULT_TC):
    """Buat pertandingan langsung aktif untuk dua pemain (matchmaking)."""
    base, inc = TIME_CONTROLS[tc_key]
    white_id, black_id = (user_a, user_b) if random.random() < 0.5 else (user_b, user_a)
    code = generate_room_code(db)
    with db:
        _cancel_waiting_rooms(db, user_a)
        _cancel_waiting_rooms(db, user_b)
        db.execute(
            "INSERT INTO games (room_code, white_id, black_id, status, time_control_seconds, "
            f"increment_seconds, started_at, white_rating_before, black_rating_before) "
            f"VALUES (?, ?, ?, 'active', ?, ?, {NOW_SQL}, "
            "(SELECT rating FROM users WHERE id = ?), (SELECT rating FROM users WHERE id = ?))",
            (code, white_id, black_id, base, inc, white_id, black_id),
        )
    return code


# ===== Aksi permainan =====

def finish_game(db, game, winner, reason):
    """Akhiri game. winner: 'white' / 'black' / 'draw'. Menghitung rating (Elo)."""
    if game.result is not None:
        return

    rating_w = db.execute("SELECT rating FROM users WHERE id = ?", (game.white_id,)).fetchone()["rating"]
    rating_b = db.execute("SELECT rating FROM users WHERE id = ?", (game.black_id,)).fetchone()["rating"]

    score_w = {"white": 1.0, "black": 0.0, "draw": 0.5}[winner]
    expected_w = 1 / (1 + 10 ** ((rating_b - rating_w) / 400))
    delta = round(32 * (score_w - expected_w))
    new_w = max(100, rating_w + delta)
    new_b = max(100, rating_b - delta)

    with db:
        for uid, color, new_rating in (
            (game.white_id, "white", new_w),
            (game.black_id, "black", new_b),
        ):
            db.execute(
                "UPDATE users SET rating = ?, games_played = games_played + 1, "
                "wins = wins + ?, losses = losses + ?, draws = draws + ? WHERE id = ?",
                (
                    new_rating,
                    int(winner == color),
                    int(winner not in (color, "draw")),
                    int(winner == "draw"),
                    uid,
                ),
            )
        db.execute(
            "UPDATE games SET status = 'finished', result = ?, result_reason = ?, current_fen = ?, "
            "white_rating_before = ?, black_rating_before = ?, white_rating_after = ?, "
            f"black_rating_after = ?, ended_at = {NOW_SQL}, "
            "duration_seconds = CAST((julianday('now') - julianday(started_at)) * 86400 AS INTEGER) "
            "WHERE id = ?",
            (winner, reason, game.board.fen(), rating_w, rating_b, new_w, new_b, game.id),
        )

    game.status = "finished"
    game.running = None
    game.draw_offer_by = None
    game.result = {
        "winner": winner,
        "reason": reason,
        "rating_changes": {"white": new_w - rating_w, "black": new_b - rating_b},
    }
    game.refresh_players(db)


def _finish_on_time(db, game, loser_color):
    winner = opposite(loser_color)
    winner_chess_color = chess.WHITE if winner == "white" else chess.BLACK
    if game.board.has_insufficient_material(winner_chess_color):
        finish_game(db, game, "draw", "timeout_insufficient")
    else:
        finish_game(db, game, winner, "timeout")


def apply_move(db, game, user_id, from_sq, to_sq, promotion):
    """Validasi dan jalankan satu langkah. Mengembalikan (berhasil, pesan_error)."""
    with game.lock:
        color = game.color_of(user_id)
        if color is None:
            return False, "Kamu bukan pemain di room ini."
        if game.status != "active" or game.result is not None:
            return False, "Permainan tidak sedang berlangsung."
        if game.running is None:
            return False, "Menunggu kedua pemain terhubung."

        turn = "white" if game.board.turn else "black"
        if color != turn:
            return False, "Bukan giliranmu."

        if game.remaining(color) <= 0:
            _finish_on_time(db, game, color)
            return False, "Waktumu habis."

        if from_sq not in chess.SQUARE_NAMES or to_sq not in chess.SQUARE_NAMES:
            return False, "Langkah tidak valid."
        promo = promotion if promotion in ("q", "r", "b", "n") else ""
        try:
            move = chess.Move.from_uci(from_sq + to_sq + promo)
        except ValueError:
            return False, "Langkah tidak valid."
        if move not in game.board.legal_moves:
            return False, "Langkah tidak sah."

        # Hitung jam
        old_clocks = (game.white_ms, game.black_ms)
        elapsed_ms = (time.monotonic() - game.turn_started) * 1000
        current_ms = game.white_ms if color == "white" else game.black_ms
        game.set_ms(color, max(0, current_ms - elapsed_ms) + game.inc_ms)

        san = game.board.san(move)
        game.board.push(move)
        ply = len(game.board.move_stack)

        try:
            with db:
                db.execute(
                    "INSERT INTO moves (game_id, ply, san, uci, fen_after, white_time_ms, "
                    "black_time_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (game.id, ply, san, move.uci(), game.board.fen(), game.white_ms, game.black_ms),
                )
                db.execute(
                    "UPDATE games SET current_fen = ? WHERE id = ?", (game.board.fen(), game.id)
                )
        except sqlite3.IntegrityError:
            game.board.pop()
            game.white_ms, game.black_ms = old_clocks
            return False, "Langkah ganda ditolak."

        game.sans.append(san)
        game.last_move = (chess.square_name(move.from_square), chess.square_name(move.to_square))
        game.draw_offer_by = None

        outcome = game.board.outcome(claim_draw=True)
        if outcome is not None:
            if outcome.winner is None:
                winner = "draw"
            else:
                winner = "white" if outcome.winner else "black"
            finish_game(db, game, winner, outcome.termination.name.lower())
        else:
            game.running = "white" if game.board.turn else "black"
            game.turn_started = time.monotonic()
        return True, None


def resign(db, game, user_id):
    with game.lock:
        color = game.color_of(user_id)
        if color is None or game.status != "active" or game.result is not None:
            return False, "Tidak bisa menyerah sekarang."
        finish_game(db, game, opposite(color), "resignation")
        return True, None


def offer_draw(db, game, user_id):
    with game.lock:
        color = game.color_of(user_id)
        if color is None or game.status != "active" or game.result is not None:
            return False, "Tidak bisa menawarkan seri sekarang."
        if game.draw_offer_by == opposite(color):
            finish_game(db, game, "draw", "agreement")
            return True, None
        game.draw_offer_by = color
        return True, None


def respond_draw(db, game, user_id, accept):
    with game.lock:
        color = game.color_of(user_id)
        if color is None or game.status != "active" or game.result is not None:
            return False, "Tidak ada tawaran seri."
        if game.draw_offer_by != opposite(color):
            return False, "Tidak ada tawaran seri dari lawan."
        if accept:
            finish_game(db, game, "draw", "agreement")
        else:
            game.draw_offer_by = None
        return True, None


def check_timeouts(db):
    """Dipanggil tiap detik: akhiri game yang waktunya habis atau pemainnya terputus."""
    changed = []
    now = time.monotonic()
    with _games_lock:
        games = list(_games.values())
    for game in games:
        with game.lock:
            if game.status != "active" or game.result is not None:
                continue
            if game.running and game.remaining(game.running) <= 0:
                _finish_on_time(db, game, game.running)
                changed.append(game)
                continue
            for color in COLORS:
                since = game.disconnected_at[color]
                if since is not None and now - since > DISCONNECT_LIMIT:
                    finish_game(db, game, opposite(color), "disconnect")
                    changed.append(game)
                    break
    return changed


# ===== Chat =====

def get_chat_history(db, game_id, limit=50):
    rows = db.execute(
        "SELECT m.user_id, m.body, m.created_at, u.username FROM messages m "
        "JOIN users u ON u.id = m.user_id WHERE m.game_id = ? ORDER BY m.id DESC LIMIT ?",
        (game_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def save_chat(db, game, user_id, username, body):
    with db:
        cursor = db.execute(
            "INSERT INTO messages (game_id, user_id, body) VALUES (?, ?, ?)",
            (game.id, user_id, body),
        )
    row = db.execute("SELECT created_at FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return {
        "user_id": user_id,
        "username": username,
        "body": body,
        "created_at": row["created_at"],
    }