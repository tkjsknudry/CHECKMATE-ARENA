"""Application factory CHECKMATE ARENA."""

from flask import Flask

from app import database
from app.extensions import socketio
from app.utils.auth import csrf_token
from config import BASE_DIR, INSTANCE_DIR, Config


def create_app(config_class=Config):
    app = Flask(
        __name__,
        instance_path=str(INSTANCE_DIR),
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_object(config_class)

    database.init_app(app)
    socketio.init_app(app, async_mode=app.config["SOCKETIO_ASYNC_MODE"])

    # Fungsi csrf_token() bisa dipakai di semua template
    app.jinja_env.globals["csrf_token"] = csrf_token

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.game import game_bp
    from app.routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(game_bp)

    # Mendaftarkan semua handler Socket.IO
    from app.sockets import game as _game_sockets  # noqa: F401

    return app