
from flask import Flask, jsonify
from flask_socketio import SocketIO

app = Flask(__name__)

app.config["SECRET_KEY"] = "checkmate-arena-local-key"

# Gunakan threading agar kompatibel dengan Windows
socketio = SocketIO(
    app,
    cors_allowed_origins=[],
    async_mode="threading"
)

@app.route("/")
def home():
    return """
    <h1>CHECKMATE ARENA</h1>
    <p>Game server berhasil dijalankan!</p>
    """

@app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "game": "CHECKMATE ARENA",
        "server": "Windows 10"
    })

if __name__ == "__main__":
    print("=" * 45)
    print("       CHECKMATE ARENA SERVER")
    print("=" * 45)
    print("Local:   http://127.0.0.1:5000")
    print("Network: http://172.16.17.71:5000")
    print("=" * 45)

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True
    )
