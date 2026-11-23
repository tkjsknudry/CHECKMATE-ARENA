"""Route dasar: pengalihan beranda dan health check."""

import sys

import chess
from flask import Blueprint, jsonify, redirect, url_for

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return redirect(url_for("dashboard.index"))


@main_bp.route("/health")
def health():
    return jsonify({
        "status": "online",
        "game": "CHECKMATE ARENA",
        "python": sys.version.split()[0],
        "python_chess": getattr(chess, "__version__", "unknown"),
    })