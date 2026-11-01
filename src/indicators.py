"""Indikator teknis lokal (pure Python, tanpa numpy).

Menghitung sinyal untuk 9 metode tambahan:
  ema200, ema50200, macd, ichimoku, ichimokutk, fibonacci,
  trenm5 (trend singkat), momentummy (momentum/ROC), lanjutimpuls (impulse continuation).

Setiap indikator menghasilkan sinyal: +1 bullish, -1 bearish, 0 netral.
Sinyal di-aggregasi menjadi Buy Power % dan Sell Power %, dengan bobot
berdasarkan mode trading (3 timeframe) dan metode analisis pilihan.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Primitive
# ---------------------------------------------------------------------------
def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def ema_series(values: list[float], period: int) -> list[float]:
    """Return full EMA series (same length, leading None diisi dengan SMA)."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = []
    e = sum(values[:period]) / period
    for i, v in enumerate(values):
        if i < period - 1:
            out.append(sum(values[: i + 1]) / (i + 1))
        elif i == period - 1:
            out.append(e)
        else:
            e = v * k + e * (1 - k)
            out.append(e)
    return out


def _slope(values: list[float], n: int = 10) -> float:
    """Slope regresi linier sederhana dari n titik terakhir (positif = naik)."""
    pts = values[-n:] if len(values) >= n else values
    m = len(pts)
    if m < 2:
        return 0.0
    xs = list(range(m))
    mx = sum(xs) / m
    my = sum(pts) / m
    num = sum((x - mx) * (y - my) for x, y in zip(xs, pts))
    den = sum((x - mx) ** 2 for x in xs) or 1
    return num / den


# ---------------------------------------------------------------------------
# Sinyal tiap indikator — return {"signal": +1/0/-1, "detail": str, "value": float|None}
# ---------------------------------------------------------------------------
def sig_ema200(candles: list[dict]) -> dict:
    closes = [c["close"] for c in candles]
    e = ema(closes, 200)
    if e is None:
        return {"signal": 0, "detail": "data kurang", "value": None}
    price = closes[-1]
    sig = 1 if price > e else -1
    pos = "di atas" if sig > 0 else "di bawah"
    return {"signal": sig, "detail": f"harga {pos} EMA200 ({e:.5f})", "value": e}


def sig_ema50200(candles: list[dict]) -> dict:
    closes = [c["close"] for c in candles]
    e50, e200 = ema(closes, 50), ema(closes, 200)
    if e50 is None or e200 is None:
        return {"signal": 0, "detail": "data kurang", "value": None}
    sig = 1 if e50 > e200 else -1
    cross = "Golden Cross" if sig > 0 else "Death Cross"
    return {"signal": sig, "detail": f"{cross} (EMA50 {e50:.5f} vs EMA200 {e200:.5f})",
            "value": e50 - e200}


def sig_macd(candles: list[dict]) -> dict:
    closes = [c["close"] for c in candles]
    if len(closes) < 35:
        return {"signal": 0, "detail": "data kurang", "value": None}
    e12 = ema_series(closes, 12)
    e26 = ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(e12[-len(e26):], e26)]
    signal_line = ema_series(macd_line, 9)
    if not signal_line:
        return {"signal": 0, "detail": "data kurang", "value": None}
    macd_now, sig_now = macd_line[-1], signal_line[-1]
    hist = macd_now - sig_now
    sig = 1 if (macd_now > sig_now and hist > 0) else -1 if (macd_now < sig_now and hist < 0) else 0
    return {"signal": sig, "detail": f"MACD {macd_now:.5f} vs signal {sig_now:.5f} (hist {hist:+.5f})",
            "value": hist}


def _ichimoku_vals(candles: list[dict]) -> dict | None:
    if len(candles) < 52:
        return None
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    def hh(n): return max(highs[-n:])
    def ll(n): return min(lows[-n:])
    tenkan = (hh(9) + ll(9)) / 2
    kijun = (hh(26) + ll(26)) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (hh(52) + ll(52)) / 2
    return {"tenkan": tenkan, "kijun": kijun, "senkou_a": senkou_a, "senkou_b": senkou_b}


def sig_ichimoku(candles: list[dict]) -> dict:
    ik = _ichimoku_vals(candles)
    if ik is None:
        return {"signal": 0, "detail": "data kurang", "value": None}
    price = candles[-1]["close"]
    cloud_top, cloud_bottom = max(ik["senkou_a"], ik["senkou_b"]), min(ik["senkou_a"], ik["senkou_b"])
    above_cloud = price > cloud_top
    tk_bull = ik["tenkan"] > ik["kijun"]
    sig = 1 if (above_cloud and tk_bull) else -1 if (price < cloud_bottom and not tk_bull) else 0
    pos = "di atas cloud" if above_cloud else "di bawah cloud" if price < cloud_bottom else "di dalam cloud"
    return {"signal": sig, "detail": f"harga {pos}; Tenkan {ik['tenkan']:.5f} / Kijun {ik['kijun']:.5f}",
            "value": price - cloud_top}


def sig_ichimokutk(candles: list[dict]) -> dict:
    ik = _ichimoku_vals(candles)
    if ik is None:
        return {"signal": 0, "detail": "data kurang", "value": None}
    sig = 1 if ik["tenkan"] > ik["kijun"] else -1
    cross = "Tenkan > Kijun (bullish)" if sig > 0 else "Kijun > Tenkan (bearish)"
    return {"signal": sig, "detail": cross, "value": ik["tenkan"] - ik["kijun"]}


def fibonacci_levels(candles: list[dict]) -> dict | None:
    """Tentukan swing high/low terakhir lalu level retracement fibonacci."""
    if len(candles) < 20:
        return None
    lookback = min(60, len(candles))
    seg = candles[-lookback:]
    hi = max(c["high"] for c in seg)
    lo = min(c["low"] for c in seg)
    if hi == lo:
        return None
    # Tentukan arah swing: posisi candle terakhir vs mid
    price = candles[-1]["close"]
    uptrend = price >= (hi + lo) / 2  # swing naik: retracement dari hi ke lo
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    if uptrend:
        levels = {r: hi - (hi - lo) * r for r in ratios}
        return {"uptrend": True, "swing_high": hi, "swing_low": lo, "levels": levels, "price": price}
    levels = {r: lo + (hi - lo) * r for r in ratios}
    return {"uptrend": False, "swing_high": hi, "swing_low": lo, "levels": levels, "price": price}


def sig_fibonacci(candles: list[dict]) -> dict:
    fib = fibonacci_levels(candles)
    if fib is None:
        return {"signal": 0, "detail": "data kurang", "value": None}
    price = fib["price"]
    lv = fib["levels"]
    # Zona golden pocket 0.5 - 0.618
    z_lo, z_hi = min(lv[0.5], lv[0.618]), max(lv[0.5], lv[0.618])
    in_zone = z_lo <= price <= z_hi
    if fib["uptrend"]:
        sig = 1 if in_zone else 0 if price > lv[0.236] else -1
        detail = f"uptrend, harga {'di zona beli 0.5-0.618' if in_zone else f'luar zona (Fib 0.5={lv[0.5]:.5f})'}"
    else:
        sig = -1 if in_zone else 0 if price < lv[0.236] else 1
        detail = f"downtrend, harga {'di zona jual 0.5-0.618' if in_zone else f'luar zona (Fib 0.5={lv[0.5]:.5f})'}"
    return {"signal": sig, "detail": detail, "value": price}


def sig_trenm5(candles: list[dict]) -> dict:
    """Trend singkat: slope EMA20 10 periode terakhir."""
    closes = [c["close"] for c in candles]
    e20 = ema_series(closes, 20)
    if len(e20) < 10:
        return {"signal": 0, "detail": "data kurang", "value": None}
    s = _slope(e20, 10)
    sig = 1 if s > 0 else -1 if s < 0 else 0
    arah = "naik" if sig > 0 else "turun" if sig < 0 else "datar"
    return {"signal": sig, "detail": f"slope EMA20 {arah} ({s:+.6f}/candle)", "value": s}


def sig_momentummy(candles: list[dict]) -> dict:
    """Momentum: Rate of Change 10 periode."""
    closes = [c["close"] for c in candles]
    if len(closes) < 11:
        return {"signal": 0, "detail": "data kurang", "value": None}
    roc = (closes[-1] - closes[-11]) / closes[-11] * 100
    sig = 1 if roc > 0.1 else -1 if roc < -0.1 else 0
    return {"signal": sig, "detail": f"ROC(10) = {roc:+.2f}%", "value": roc}


def sig_lanjutimpuls(candles: list[dict]) -> dict:
    """Impulse continuation: 3 candle terakhir badan besar searah & close di ekstrem."""
    if len(candles) < 8:
        return {"signal": 0, "detail": "data kurang", "value": None}
    bodies = [abs(c["close"] - c["open"]) for c in candles[-8:]]
    avg_body = sum(bodies[:-3]) / max(1, len(bodies) - 3) or 1e-9
    last3 = candles[-3:]
    bull = sum(1 for c in last3 if c["close"] > c["open"] and (c["close"] - c["open"]) > avg_body)
    bear = sum(1 for c in last3 if c["close"] < c["open"] and (c["open"] - c["close"]) > avg_body)
    if bull >= 2 and bull > bear:
        return {"signal": 1, "detail": f"impuls bullish berlanjut ({bull}/3 candle hijau besar)", "value": bull}
    if bear >= 2 and bear > bull:
        return {"signal": -1, "detail": f"impuls bearish berlanjut ({bear}/3 candle merah besar)", "value": -bear}
    return {"signal": 0, "detail": "tidak ada impuls kuat berlanjut", "value": 0}


INDICATORS = [
    ("ema200", sig_ema200, "structure"),
    ("ema50200", sig_ema50200, "structure"),
    ("macd", sig_macd, "momentum"),
    ("ichimoku", sig_ichimoku, "ichimoku"),
    ("ichimokutk", sig_ichimokutk, "ichimoku"),
    ("fibonacci", sig_fibonacci, "structure"),
    ("trenm5", sig_trenm5, "structure"),
    ("momentummy", sig_momentummy, "momentum"),
    ("lanjutimpuls", sig_lanjutimpuls, "momentum"),
]

# Bobot indikator berdasarkan metode analisis pilihan (keluarga indikator)
METHOD_WEIGHT = {
    "SND": {"structure": 1.4, "momentum": 1.0, "ichimoku": 1.0},
    "SNR": {"structure": 1.4, "momentum": 1.0, "ichimoku": 1.0},
    "SMC": {"structure": 1.2, "momentum": 1.1, "ichimoku": 1.2},
    "ICT": {"structure": 1.2, "momentum": 1.1, "ichimoku": 1.2},
    "KILLZONE": {"structure": 1.0, "momentum": 1.4, "ichimoku": 1.0},
}

# Bobot timeframe per mode trading: (entry, confirm, trend)
MODE_TF_WEIGHT = {
    "Scalping": (0.50, 0.35, 0.15),
    "Intraday": (0.35, 0.40, 0.25),
    "Swing": (0.20, 0.35, 0.45),
}


@dataclass
class PowerResult:
    buy_pct: float = 0.0
    sell_pct: float = 0.0
    neutral_pct: float = 0.0
    signals: list[dict] = field(default_factory=list)  # {name, tf, signal, detail, weight}
    buyer_area: tuple[float, float] | None = None
    seller_area: tuple[float, float] | None = None
    key_levels: list[float] = field(default_factory=list)


def compute_power(candles_tf: dict[str, list[dict]], trading_mode: str,
                  analysis_method: str) -> PowerResult:
    """Aggregate sinyal indikator lintas 3 timeframe → buy/sell power."""
    res = PowerResult()
    tf_weights = MODE_TF_WEIGHT.get(trading_mode, (0.34, 0.33, 0.33))
    fam_weights = METHOD_WEIGHT.get(analysis_method.upper(),
                                    {"structure": 1.0, "momentum": 1.0, "ichimoku": 1.0})
    tf_names = list(candles_tf.keys())  # [entry, confirm, trend]
    total_w = 0.0
    bull_w = 0.0
    bear_w = 0.0

    levels = []
    for tf_name, candles in candles_tf.items():
        idx = tf_names.index(tf_name) if tf_name in tf_names else 1
        tf_w = tf_weights[idx] if idx < 3 else 0.33
        for name, fn, family in INDICATORS:
            try:
                out = fn(candles)
            except Exception:  # noqa: BLE001 — indikator gagal = netral, jangan crash
                out = {"signal": 0, "detail": "error perhitungan", "value": None}
            w = tf_w * fam_weights.get(family, 1.0)
            sig = out.get("signal", 0)
            total_w += w
            if sig > 0:
                bull_w += w
            elif sig < 0:
                bear_w += w
            res.signals.append({"name": name, "tf": tf_name, "signal": sig,
                                "detail": out.get("detail", ""), "weight": round(w, 3)})
            # Kumpulkan level harga untuk area buyer/seller
            v = out.get("value")
            if isinstance(v, (int, float)) and name in ("ema200",):
                levels.append(v)

    # Tambahkan level fib & ichimoku dari timeframe entry
    entry_tf = tf_names[0] if tf_names else None
    if entry_tf and entry_tf in candles_tf:
        c = candles_tf[entry_tf]
        fib = fibonacci_levels(c)
        if fib:
            levels.extend([fib["levels"][0.5], fib["levels"][0.618], fib["swing_low"], fib["swing_high"]])
        ik = _ichimoku_vals(c)
        if ik:
            levels.extend([ik["senkou_a"], ik["senkou_b"], ik["kijun"]])
        e50 = ema([x["close"] for x in c], 50)
        if e50:
            levels.append(e50)

    price = None
    if entry_tf and entry_tf in candles_tf and candles_tf[entry_tf]:
        price = candles_tf[entry_tf][-1]["close"]

    levels = sorted(set(round(x, 6) for x in levels if isinstance(x, (int, float))))
    res.key_levels = levels
    if price is not None and levels:
        below = [l for l in levels if l < price]
        above = [l for l in levels if l > price]
        if below:
            # Area buyer: zona support di bawah harga (2 level terdekat)
            lo = below[-2] if len(below) >= 2 else below[-1]
            res.buyer_area = (lo, below[-1])
        if above:
            hi = above[1] if len(above) >= 2 else above[0]
            res.seller_area = (above[0], hi)

    if total_w > 0:
        res.buy_pct = round(bull_w / total_w * 100, 1)
        res.sell_pct = round(bear_w / total_w * 100, 1)
        res.neutral_pct = round(100 - res.buy_pct - res.sell_pct, 1)
    return res
