#!/usr/bin/env python3
"""AI Trading Terminal — entry point.

Jalankan:  python main.py
"""
from __future__ import annotations

import sys

from src import config
from src.menus import main_menu
from src.ui import clear, console, error


def main() -> None:
    clear()
    config.load_env()
    try:
        main_menu()
    except KeyboardInterrupt:
        clear()
        console.print("\n[bold yellow]Dibatalkan oleh pengguna.[/]")
        sys.exit(0)
    except Exception as e:  # noqa: BLE001 — tampilkan error ramah, jangan crash mentah
        clear()
        error(f"Terjadi kesalahan tak terduga: {e}")
        console.print("[dim]Laporkan bug dengan menyertakan pesan di atas.[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
