"""Konfigurasi aplikasi: path, env, metode analisis, dan setting trade."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Root proyek (folder tempat main.py berada)
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"
SETTINGS_PATH = ROOT_DIR / "config.json"

APP_NAME = "AI TRADING TERMINAL"
APP_VERSION = "1.1.0"

# Lima metode analisis (pilih nomor 1-5)
ANALYSIS_METHODS = [
    {"id": 1, "code": "SND", "name": "Supply & Demand",
     "desc": "Fokus pada zona supply/demand (origin of move, POI, fresh zone)."},
    {"id": 2, "code": "SNR", "name": "Support & Resistance",
     "desc": "Fokus pada level support/resistance horizontal & flip level."},
    {"id": 3, "code": "SMC", "name": "Smart Money Concepts",
     "desc": "Fokus pada BOS/CHoCH, order block, FVG, liquidity sweep."},
    {"id": 4, "code": "ICT", "name": "Inner Circle Trader",
     "desc": "Fokus pada ICT core: displacement, OTE, premium/discount, PD array."},
    {"id": 5, "code": "KILLZONE", "name": "Session Killzone",
     "desc": "Fokus pada sesi London & New York killzone + high probability setups."},
]

DEFAULT_SETTINGS = {
    "risk_reward": "1:2",
    "analysis_method": "SMC",
    "target_pips": 50,
    "trading_mode": "Intraday",
}

# Mode trading = gabungan 3 timeframe: (entry, confirm, trend)
# Interval memakai format TwelveData.
TRADING_MODES = [
    {"id": 1, "code": "Scalping", "timeframes": ("5min", "30min", "1h"),
     "desc": "Entry cepat M5 + konfirmasi M30 + arah tren H1."},
    {"id": 2, "code": "Intraday", "timeframes": ("15min", "1h", "4h"),
     "desc": "Entry M15 + konfirmasi H1 + arah tren H4."},
    {"id": 3, "code": "Swing", "timeframes": ("1h", "1day", "1week"),
     "desc": "Entry H1 + konfirmasi D1 + arah tren W1 (beberapa hari)."},
]

TF_LABELS = ("Entry", "Konfirmasi", "Tren")

# Timeframe yang valid untuk TwelveData (referensi)
VALID_TIMEFRAMES = [
    "1min", "5min", "15min", "30min", "45min",
    "1h", "2h", "4h", "8h", "1day", "1week", "1month",
]


def trading_mode_by_code(code: str) -> dict | None:
    for m in TRADING_MODES:
        if m["code"].lower() == code.lower():
            return m
    return None


def method_by_code(code: str) -> dict | None:
    for m in ANALYSIS_METHODS:
        if m["code"].upper() == code.upper():
            return m
    return None


def load_env() -> None:
    """Load .env (buat dari .env.example bila belum ada)."""
    if not ENV_PATH.exists() and ENV_EXAMPLE_PATH.exists():
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    load_dotenv(ENV_PATH, override=True)


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_SETTINGS)
            merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def keys_status() -> dict[str, bool]:
    """Cek apakah tiap API key sudah diisi."""
    return {
        "GROQ_API_KEY": bool(env("GROQ_API_KEY").strip()),
        "TWELVEDATA_API_KEY": bool(env("TWELVEDATA_API_KEY").strip()),
        "SOSOVALUE_API_KEY": bool(env("SOSOVALUE_API_KEY").strip()),
    }
