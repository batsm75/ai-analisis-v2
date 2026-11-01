"""Client API: TwelveData, SoSoValue, dan Groq (OpenAI-compatible)."""
from __future__ import annotations

import json
from typing import Any

import requests

from . import config

TIMEOUT = 25


class APIError(Exception):
    pass


# ---------------------------------------------------------------------------
# TwelveData — data market utama (forex / saham / crypto / indeks)
# ---------------------------------------------------------------------------
class TwelveDataClient:
    def __init__(self) -> None:
        self.api_key = config.env("TWELVEDATA_API_KEY").strip()
        self.base_url = config.env("TWELVEDATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")

    def ready(self) -> bool:
        return bool(self.api_key)

    def get_candles(self, symbol: str, interval: str, outputsize: int = 120) -> list[dict]:
        """Return list candle terbaru (terbaru di akhir): {time, open, high, low, close}."""
        if not self.ready():
            raise APIError("TWELVEDATA_API_KEY belum diisi. Buka menu [3] Env.")
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
            "format": "JSON",
        }
        try:
            r = requests.get(f"{self.base_url}/time_series", params=params, timeout=TIMEOUT)
            data = r.json()
        except requests.RequestException as e:
            raise APIError(f"Gagal koneksi ke TwelveData: {e}") from e
        except ValueError:
            raise APIError("Respons TwelveData bukan JSON.")

        if isinstance(data, dict) and data.get("code") and data.get("code") != 200:
            raise APIError(f"TwelveData: {data.get('message', 'error')}")
        values = data.get("values") if isinstance(data, dict) else None
        if not values:
            raise APIError("Tidak ada data candle (periksa simbol & timeframe).")

        candles = []
        for v in reversed(values):  # terlama -> terbaru
            try:
                candles.append({
                    "time": v.get("datetime", ""),
                    "open": float(v["open"]),
                    "high": float(v["high"]),
                    "low": float(v["low"]),
                    "close": float(v["close"]),
                })
            except (KeyError, ValueError, TypeError):
                continue
        if not candles:
            raise APIError("Data candle tidak valid.")
        return candles


# ---------------------------------------------------------------------------
# SoSoValue v3 — data tambahan (US equity & perpetual futures)
# ---------------------------------------------------------------------------
class SoSoValueClient:
    def __init__(self) -> None:
        self.api_key = config.env("SOSOVALUE_API_KEY").strip()
        self.base_url = config.env("SOSOVALUE_BASE_URL",
                                   "https://openapi.sosovalue.com/openapi/v3").rstrip("/")

    def ready(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _map_interval(interval: str) -> str:
        mapping = {
            "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "8h": "8h",
            "1day": "1d", "1week": "1w", "1month": "1M",
        }
        return mapping.get(interval, "1h")

    @staticmethod
    def _extract_candles(payload: Any) -> list[dict]:
        """Parser defensif — bentuk data bisa bervariasi."""
        if isinstance(payload, dict):
            for key in ("candles", "data", "list", "results", "klines"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            return []
        out = []
        for c in payload:
            if not isinstance(c, dict):
                continue
            o = c.get("open", c.get("o"))
            h = c.get("high", c.get("h"))
            l = c.get("low", c.get("l"))
            cl = c.get("close", c.get("c"))
            t = c.get("time", c.get("ts", c.get("datetime", "")))
            try:
                out.append({"time": str(t), "open": float(o), "high": float(h),
                            "low": float(l), "close": float(cl)})
            except (TypeError, ValueError):
                continue
        return out

    def get_candles(self, instrument_ref: str, interval: str, limit: int = 120):
        """Return (candles, note). Jika tidak tersedia, candles=[] dan note berisi alasan."""
        if not self.ready():
            return [], "SOSOVALUE_API_KEY belum diisi — data ini dilewati."
        iv = self._map_interval(interval)
        url = f"{self.base_url}/instruments/{instrument_ref}/candles"
        try:
            r = requests.get(url, params={"interval": iv, "limit": limit},
                             headers={"x-soso-api-key": self.api_key}, timeout=TIMEOUT)
            if r.status_code == 404:
                return [], (f"Instrument '{instrument_ref}' tidak ditemukan di SoSoValue "
                            f"(v3 hanya mendukung US equity & perpetual futures).")
            if r.status_code != 200:
                return [], f"SoSoValue HTTP {r.status_code}: {r.text[:120]}"
            payload = r.json()
        except requests.RequestException as e:
            return [], f"Gagal koneksi ke SoSoValue: {e}"
        except ValueError:
            return [], "Respons SoSoValue bukan JSON."

        if isinstance(payload, dict) and payload.get("code") not in (0, None):
            return [], f"SoSoValue: {payload.get('message', 'error')}"
        candles = self._extract_candles(payload)
        if not candles:
            return [], "SoSoValue mengembalikan data kosong / format tidak dikenal."
        return candles, "OK"


# ---------------------------------------------------------------------------
# Groq — otak AI (OpenAI-compatible chat completions)
# ---------------------------------------------------------------------------
class GroqClient:
    def __init__(self) -> None:
        self.api_key = config.env("GROQ_API_KEY").strip()
        self.base_url = config.env("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        self.model = config.env("GROQ_MODEL", "qwen/qwen3.8-27b").strip() or "qwen/qwen3.8-27b"

    def ready(self) -> bool:
        return bool(self.api_key)

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        if not self.ready():
            raise APIError("GROQ_API_KEY belum diisi. Buka menu [3] Env.")
        body = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            r = requests.post(f"{self.base_url}/chat/completions",
                              headers={"Authorization": f"Bearer {self.api_key}",
                                       "Content-Type": "application/json"},
                              data=json.dumps(body), timeout=90)
        except requests.RequestException as e:
            raise APIError(f"Gagal koneksi ke Groq: {e}") from e

        if r.status_code != 200:
            raise APIError(f"Groq HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as e:
            raise APIError(f"Respons Groq tidak valid: {e}") from e
