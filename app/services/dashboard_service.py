"""Layanan data untuk halaman dashboard."""

PLACEHOLDER = "—"


def get_leaderboard_preview(db, limit: int = 5) -> list[dict]:
    """Pemain dengan rating tertinggi (data nyata dari database)."""
    rows = db.execute(
        "SELECT username, rating, wins, avatar_color "
        "FROM users ORDER BY rating DESC, wins DESC, id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_platform_counts(db) -> dict:
    """Jumlah pemain terdaftar dan pertandingan yang sudah selesai."""
    players = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    games = db.execute("SELECT COUNT(*) FROM games WHERE status = 'finished'").fetchone()[0]
    return {"players": players, "games": games}


def build_stat_cards(player=None) -> list[dict]:
    """Empat kartu statistik pemain. Tamu (belum login) menampilkan tanda strip."""
    if player is None:
        rating = games = wins = win_rate = PLACEHOLDER
    else:
        rating = player["rating"]
        games = player["games_played"]
        wins = player["wins"]
        win_rate = round(wins / games * 100) if games else 0

    return [
        {"label": "Rating", "icon": "star", "value": rating, "suffix": ""},
        {"label": "Total Match", "icon": "grid", "value": games, "suffix": ""},
        {"label": "Menang", "icon": "trophy", "value": wins, "suffix": ""},
        {"label": "Win Rate", "icon": "percent", "value": win_rate, "suffix": "%"},
    ]