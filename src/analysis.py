"""Engine analisis: gabungkan data market (3 timeframe) -> indikator lokal
(buy/sell power + area buyer/seller) -> kirim ke Groq -> hasilkan setup."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import config
from .clients import APIError, GroqClient, SoSoValueClient, TwelveDataClient
from .indicators import PowerResult, compute_power


@dataclass
class AnalysisResult:
    symbol: str = ""
    trading_mode: str = ""
    timeframes: tuple = ()
    current_price: float | None = None
    candles_per_tf: dict = field(default_factory=dict)   # {"Entry": [...], ...}
    twelvedata_ok: bool = False
    sosovalue_note: str = ""
    sosovalue_count: int = 0
    stats: dict = field(default_factory=dict)
    power: PowerResult | None = None
    ai_raw: str = ""
    setup: dict | None = None
    error: str = ""


def _candles_to_text(candles: list[dict], limit: int = 50) -> str:
    subset = candles[-limit:]
    lines = ["time,O,H,L,C"]
    for c in subset:
        lines.append(f"{c['time']},{c['open']},{c['high']},{c['low']},{c['close']}")
    return "\n".join(lines)


def _compute_stats(candles: list[dict]) -> dict:
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    last = candles[-1]
    ma20 = sum(closes[-20:]) / min(20, len(closes))
    swing_high = max(highs[-30:]) if len(highs) >= 5 else max(highs)
    swing_low = min(lows[-30:]) if len(lows) >= 5 else min(lows)
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[-14:]) / max(1, len(trs[-14:])) if trs else 0
    return {
        "last_time": last["time"],
        "last_close": last["close"],
        "ma20": round(ma20, 6),
        "swing_high_30": round(swing_high, 6),
        "swing_low_30": round(swing_low, 6),
        "atr14": round(atr, 6),
        "bias_ma": "ABOVE MA20 (bullish)" if last["close"] > ma20 else "BELOW MA20 (bearish)",
    }


def _extract_json(text: str) -> dict | None:
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1)
    else:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1 and end > start:
            t = t[start:end + 1]
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _power_summary(power: PowerResult) -> str:
    lines = [f"BUY POWER: {power.buy_pct}% | SELL POWER: {power.sell_pct}% | "
             f"NETRAL: {power.neutral_pct}%"]
    if power.buyer_area:
        lines.append(f"AREA PEMBELI (buyer zone): {power.buyer_area[0]} - {power.buyer_area[1]}")
    if power.seller_area:
        lines.append(f"AREA PENJUAL (seller zone): {power.seller_area[0]} - {power.seller_area[1]}")
    # Ringkasan sinyal per indikator (gabungan lintas TF)
    agg: dict[str, int] = {}
    for s in power.signals:
        agg[s["name"]] = agg.get(s["name"], 0) + s["signal"]
    lines.append("Sinyal indikator (total skor lintas 3 TF, + bullish / - bearish):")
    for name, score in agg.items():
        arah = "BULLISH" if score > 0 else "BEARISH" if score < 0 else "NETRAL"
        lines.append(f"  - {name}: {arah} ({score:+d})")
    return "\n".join(lines)


def _build_prompts(symbol: str, mode: dict, candles_entry: list[dict],
                   stats: dict, settings: dict, power: PowerResult) -> tuple[str, str]:
    method = config.method_by_code(settings["analysis_method"])
    method_name = method["name"] if method else settings["analysis_method"]
    method_desc = method["desc"] if method else ""
    tfs = mode["timeframes"]

    system = (
        "Kamu adalah analis teknikal profesional spesialis forex & crypto. "
        "Kamu menerima data candle + hasil perhitungan indikator teknis (buy/sell power, "
        "area buyer/seller) lintas 3 timeframe. Identifikasi struktur pasar & chart pattern, "
        "lalu hasilkan satu setup trading yang jelas. Jawab HANYA dalam format JSON, tanpa teks lain. "
        "Field wajib: setup (BUY/SELL/WAIT), pattern (nama pola), confidence (0-100), "
        "entry, stop_loss, take_profit (array 1-3 level), risk_reward, "
        "invalidation, key_levels (array level penting), bias (arah tren), "
        "buy_power_pct, sell_power_pct (ulang angka dari data), "
        "reasoning (3-5 poin, bahasa Indonesia, sebutkan area buyer/seller bila relevan)."
    )

    candle_text = _candles_to_text(candles_entry)
    user = f"""INSTRUMEN: {symbol}
MODE TRADING: {mode['code']} — timeframe Entry={tfs[0]}, Konfirmasi={tfs[1]}, Tren={tfs[2]}
METODE ANALISIS: {method_name} — {method_desc}
PENGATURAN TRADE: Risk:Reward = {settings['risk_reward']}, Target = {settings['target_pips']} pips

HASIL INDIKATOR TEKNIS (9 metode: ema200, ema50200, macd, ichimoku, ichimokutk, fibonacci, trenm5, momentummy, lanjutimpuls):
{_power_summary(power)}

STATISTIK TF ENTRY:
- Close terakhir: {stats['last_close']} @ {stats['last_time']}
- MA20: {stats['ma20']} → harga {stats['bias_ma']}
- Swing high (30 candle): {stats['swing_high_30']}
- Swing low (30 candle): {stats['swing_low_30']}
- ATR14 (volatilitas): {stats['atr14']}

DATA CANDLE TF ENTRY (terlama → terbaru, format time,O,H,L,C):
{candle_text}

Berdasarkan mode {mode['code']}, metode {method_name}, serta buy/sell power & area buyer/seller di atas,
tentukan setup terbaik saat ini. Jika buy power & sell power seimbang atau tidak ada setup valid,
isi setup="WAIT". Pastikan entry, stop_loss, take_profit masuk akal terhadap harga, ATR, dan area buyer/seller.
Jawab HANYA JSON."""
    return system, user


def run_analysis(symbol: str, settings: dict) -> AnalysisResult:
    mode = config.trading_mode_by_code(settings.get("trading_mode", "Intraday")) or config.TRADING_MODES[1]
    res = AnalysisResult(symbol=symbol.upper(), trading_mode=mode["code"],
                         timeframes=mode["timeframes"])

    # 1. Ambil 3 timeframe dari TwelveData (butuh ~260 candle untuk EMA200)
    td = TwelveDataClient()
    if not td.ready():
        res.error = "TWELVEDATA_API_KEY belum diisi. Buka menu [3] Env."
        return res

    candles_per_tf: dict[str, list[dict]] = {}
    errors = []
    for label, interval in zip(config.TF_LABELS, mode["timeframes"]):
        try:
            candles_per_tf[label] = td.get_candles(symbol, interval, outputsize=260)
        except APIError as e:
            errors.append(f"{label}({interval}): {e}")
    if not candles_per_tf:
        res.error = "Gagal mengambil data TwelveData: " + "; ".join(errors)
        return res

    res.twelvedata_ok = True
    res.candles_per_tf = candles_per_tf
    entry_candles = candles_per_tf.get("Entry") or next(iter(candles_per_tf.values()))
    res.current_price = entry_candles[-1]["close"]
    res.stats = _compute_stats(entry_candles)

    # 2. Hitung buy/sell power + area buyer/seller dari indikator lokal
    try:
        res.power = compute_power(candles_per_tf, mode["code"], settings["analysis_method"])
    except Exception as e:  # noqa: BLE001 — jangan sampai gagal indikator menggagalkan analisis
        res.power = PowerResult()
        res.error = f"(warning) perhitungan indikator gagal: {e}"

    # 3. SoSoValue (tambahan, opsional) — pakai interval entry
    ssv = SoSoValueClient()
    if ssv.ready():
        entry_interval = mode["timeframes"][0]
        ssv_candles, note = ssv.get_candles(symbol, entry_interval, limit=140)
        res.sosovalue_note = note
        res.sosovalue_count = len(ssv_candles)
    else:
        res.sosovalue_note = "SOSOVALUE_API_KEY belum diisi — data ini dilewati."

    # 4. Analisis oleh Groq
    groq = GroqClient()
    if not groq.ready():
        res.error = (res.error + " | " if res.error else "") + "GROQ_API_KEY belum diisi. Buka menu [3] Env."
        return res

    system, user = _build_prompts(symbol, mode, entry_candles, res.stats, settings, res.power)
    try:
        raw = groq.chat(system, user)
        res.ai_raw = raw
        res.setup = _extract_json(raw)
    except APIError as e:
        res.error = (res.error + " | " if res.error else "") + str(e)
    return res
