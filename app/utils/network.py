"""Utilitas jaringan."""

import socket


def get_local_ip() -> str:
    """Kembalikan IP lokal perangkat di jaringan (LAN)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Tidak ada data yang benar-benar dikirim; hanya untuk membaca IP yang dipakai.
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()