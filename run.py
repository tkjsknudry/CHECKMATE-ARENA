"""Titik masuk untuk menjalankan server CHECKMATE ARENA."""

from app import create_app
from app.extensions import socketio
from app.sockets.game import start_background_loop
from app.utils.network import get_local_ip

app = create_app()

if __name__ == "__main__":
    host = app.config["HOST"]
    port = app.config["PORT"]
    local_ip = get_local_ip()

    print("=" * 45)
    print("       CHECKMATE ARENA SERVER")
    print("=" * 45)
    print(f"Local:   http://127.0.0.1:{port}")
    print(f"Network: http://{local_ip}:{port}")
    print("=" * 45)

    start_background_loop(app)

    socketio.run(
        app,
        host=host,
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )