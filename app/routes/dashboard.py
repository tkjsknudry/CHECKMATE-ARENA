"""Route halaman dashboard."""

from flask import Blueprint, g, render_template

from app.database import get_db
from app.services import game_service
from app.services.dashboard_service import (
    build_stat_cards,
    get_leaderboard_preview,
    get_platform_counts,
)
from app.utils.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    db = get_db()
    player = g.player

    return render_template(
        "dashboard/index.html",
        active_page="dashboard",
        player=player,
        platform=get_platform_counts(db),
        leaders=get_leaderboard_preview(db),
        stat_cards=build_stat_cards(player),
        active_game=game_service.find_open_game(db, player["id"]),
    )