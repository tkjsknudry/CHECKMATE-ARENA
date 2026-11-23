-- Skema database CHECKMATE ARENA.
-- Aman dijalankan berulang kali (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    rating          INTEGER NOT NULL DEFAULT 1200,
    games_played    INTEGER NOT NULL DEFAULT 0,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    draws           INTEGER NOT NULL DEFAULT 0,
    avatar_color    TEXT    NOT NULL DEFAULT '#c9a227',
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_login_at   TEXT,
    CHECK (length(username) BETWEEN 3 AND 20)
);

CREATE INDEX IF NOT EXISTS idx_users_rating ON users (rating DESC);

CREATE TABLE IF NOT EXISTS games (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    room_code             TEXT    NOT NULL UNIQUE,
    white_id              INTEGER REFERENCES users (id),
    black_id              INTEGER REFERENCES users (id),
    status                TEXT    NOT NULL DEFAULT 'waiting'
                          CHECK (status IN ('waiting', 'active', 'finished', 'abandoned')),
    result                TEXT    CHECK (result IN ('white', 'black', 'draw')),
    result_reason         TEXT,
    time_control_seconds  INTEGER NOT NULL DEFAULT 600,
    increment_seconds     INTEGER NOT NULL DEFAULT 0,
    current_fen           TEXT    NOT NULL
                          DEFAULT 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    white_rating_before   INTEGER,
    black_rating_before   INTEGER,
    white_rating_after    INTEGER,
    black_rating_after    INTEGER,
    created_at            TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at            TEXT,
    ended_at              TEXT,
    duration_seconds      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_games_white  ON games (white_id);
CREATE INDEX IF NOT EXISTS idx_games_black  ON games (black_id);
CREATE INDEX IF NOT EXISTS idx_games_status ON games (status);

CREATE TABLE IF NOT EXISTS moves (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id          INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    ply              INTEGER NOT NULL CHECK (ply >= 1),
    san              TEXT    NOT NULL,
    uci              TEXT    NOT NULL,
    fen_after        TEXT    NOT NULL,
    white_time_ms    INTEGER,
    black_time_ms    INTEGER,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (game_id, ply)
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users (id),
    body        TEXT    NOT NULL CHECK (length(body) BETWEEN 1 AND 300),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_game ON messages (game_id, id);