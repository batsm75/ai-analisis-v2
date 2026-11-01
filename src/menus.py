"""Semua menu aplikasi. Setiap pindah menu: clear screen dulu, lalu tampilkan menu tujuan."""
from __future__ import annotations

from dotenv import set_key
from rich.panel import Panel
from rich.table import Table

from . import config
from .analysis import run_analysis
from .ui import (ask, ask_int, banner, clear, console, env_table, error, hr,
                 info, mask_secret, power_panel, press_enter, settings_table,
                 signals_table, success, warn)

# Daftar variabel .env yang bisa diedit dari menu
ENV_EDITABLE = [
    ("GROQ_API_KEY", "Groq API Key (otak AI)", "https://console.groq.com/keys", True),
    ("GROQ_MODEL", "Groq Model AI", "default: qwen/qwen3.8-27b", False),
    ("GROQ_BASE_URL", "Groq Base URL", "https://api.groq.com/openai/v1", False),
    ("TWELVEDATA_API_KEY", "TwelveData API Key (data market)", "https://twelvedata.com/account/api-keys", True),
    ("TWELVEDATA_BASE_URL", "TwelveData Base URL", "https://api.twelvedata.com", False),
    ("SOSOVALUE_API_KEY", "SoSoValue API Key (data market v3)", "https://sosovalue.com/developer", True),
    ("SOSOVALUE_BASE_URL", "SoSoValue Base URL", "https://openapi.sosovalue.com/openapi/v3", False),
]


# ===========================================================================
# MENU UTAMA
# ===========================================================================
def main_menu() -> None:
    while True:
        banner("MENU UTAMA")
        status = config.keys_status()
        st_table = Table(show_header=False, expand=True, box=None)
        st_table.add_column(style="cyan")
        st_table.add_column()
        for k, filled in status.items():
            label = k.replace("_API_KEY", "")
            st_table.add_row(f"  {label}", "[green]✓ terisi[/]" if filled else "[red]✗ belum diisi[/]")
        console.print(Panel(st_table, title="Status API Key", border_style="magenta"))
        hr()
        console.print("[bold cyan]  1[/]  Analisis (AI membaca chart pattern)")
        console.print("[bold cyan]  2[/]  Pengaturan Trade (RR, metode, target pips)")
        console.print("[bold cyan]  3[/]  Env (API Key & URL)")
        console.print("[bold red]  0[/]  Keluar")
        hr()
        choice = ask("Pilih menu", allow_empty=False)
        if choice == "1":
            analysis_menu()
        elif choice == "2":
            trade_settings_menu()
        elif choice == "3":
            env_menu()
        elif choice == "0":
            clear()
            console.print("[bold cyan]Terima kasih telah menggunakan AI Trading Terminal.[/]")
            return
        else:
            warn("Pilihan tidak valid.")
            press_enter()


# ===========================================================================
# MENU 1 — ANALISIS
# ===========================================================================
def _display_result(res) -> None:
    console.print()
    # Status sumber data (3 timeframe)
    src = Table(show_header=False, expand=True, box=None)
    src.add_column(style="cyan", width=18)
    src.add_column()
    if res.twelvedata_ok:
        tf_info = ", ".join(f"{lbl}:{len(res.candles_per_tf.get(lbl, []))}c"
                            for lbl in config.TF_LABELS)
        src.add_row("TwelveData", f"[green]✓[/] {tf_info} • harga {res.current_price}")
    else:
        src.add_row("TwelveData", "[red]✗ gagal[/]")
    ssv_label = f"[green]✓[/] {res.sosovalue_count} candle" if res.sosovalue_count > 0 else "[yellow]![/]"
    src.add_row("SoSoValue", f"{ssv_label} — {res.sosovalue_note}")
    console.print(Panel(src, title=f"Sumber Data — {res.symbol} • Mode {res.trading_mode} "
                        f"({' / '.join(res.timeframes)})", border_style="blue"))

    # Buy / Sell power + area buyer/seller (dari 9 indikator × 3 TF)
    if res.power:
        console.print(power_panel(res.power))
        # Ringkasan sinyal per indikator (agregasi lintas TF)
        agg: dict[str, int] = {}
        for s in res.power.signals:
            agg[s["name"]] = agg.get(s["name"], 0) + s["signal"]
        sig_t = Table(show_header=True, header_style="bold magenta", expand=True)
        sig_t.add_column("Indikator", style="cyan", no_wrap=True)
        sig_t.add_column("Skor", width=8)
        sig_t.add_column("Sinyal", width=10)
        for name, score in sorted(agg.items(), key=lambda x: -abs(x[1])):
            if score > 0:
                sig_t.add_row(name, f"{score:+d}", "[green]BULLISH[/]")
            elif score < 0:
                sig_t.add_row(name, f"{score:+d}", "[red]BEARISH[/]")
            else:
                sig_t.add_row(name, "0", "[dim]NETRAL[/]")
        console.print(Panel(sig_t, title="Ringkasan 9 Indikator (akumulasi lintas 3 timeframe)",
                            border_style="cyan"))

    if res.error:
        warn(res.error)
    if not res.setup:
        if res.ai_raw:
            console.print(Panel(res.ai_raw, title="Hasil Analisis AI (mentah)",
                                border_style="yellow"))
        return

    s = res.setup
    direction = str(s.get("setup", "?")).upper()
    color = "green" if direction == "BUY" else "red" if direction == "SELL" else "yellow"
    conf = s.get("confidence", "?")

    summary = Table(show_header=False, expand=True, box=None)
    summary.add_column(style="cyan", width=20)
    summary.add_column(style="bold")
    summary.add_row("Arah Setup", f"[{color}]{direction}[/{color}]")
    summary.add_row("Pattern", str(s.get("pattern", "-")))
    summary.add_row("Confidence", f"{conf} / 100")
    summary.add_row("Bias Tren", str(s.get("bias", "-")))
    if s.get("buy_power_pct") is not None:
        summary.add_row("Buy / Sell (AI)", f"{s.get('buy_power_pct')}% / {s.get('sell_power_pct')}%")
    summary.add_row("Entry", str(s.get("entry", "-")))
    summary.add_row("Stop Loss", f"[red]{s.get('stop_loss', '-')}[/]")
    tp = s.get("take_profit", [])
    if isinstance(tp, list):
        tp_str = "  |  ".join(f"TP{i+1}: {v}" for i, v in enumerate(tp))
    else:
        tp_str = str(tp)
    summary.add_row("Take Profit", f"[green]{tp_str}[/]")
    summary.add_row("Risk : Reward", str(s.get("risk_reward", "-")))
    summary.add_row("Invalidasi", str(s.get("invalidation", "-")))
    console.print(Panel(summary, title=f"SETUP TRADE — {res.symbol} • {res.trading_mode}",
                        border_style=color))

    levels = s.get("key_levels", [])
    if isinstance(levels, list) and levels:
        lv = ", ".join(str(x) for x in levels)
        console.print(Panel(f"[cyan]Level Penting:[/] {lv}", border_style="cyan"))

    reasoning = s.get("reasoning", "")
    if isinstance(reasoning, list):
        reasoning = "\n".join(f"  • {x}" for x in reasoning)
    console.print(Panel(str(reasoning), title="Penjelasan (Reasoning)", border_style="green"))


def analysis_menu() -> None:
    symbol = ""
    settings = config.load_settings()

    while True:
        banner("MENU 1 — ANALISIS AI")
        method = config.method_by_code(settings["analysis_method"])
        mode = config.trading_mode_by_code(settings.get("trading_mode", "Intraday"))
        info(f"Mode: [bold]{mode['code']}[/] ({' / '.join(mode['timeframes'])}) • "
             f"Metode: [bold]{method['code']}[/] • RR: [bold]{settings['risk_reward']}[/] • "
             f"Target: [bold]{settings['target_pips']} pips[/]")
        hr()

        if not symbol:
            symbol = ask("Simbol / Pair (contoh: EUR/USD, GBP/USD, XAU/USD, BTC/USD, AAPL)",
                         allow_empty=False)

        console.print("\n[bold yellow]⟳ Mengambil 3 timeframe & menghitung indikator... (tunggu)[/]\n")
        res = run_analysis(symbol, settings)
        _display_result(res)

        hr()
        console.print("[bold cyan]  R[/]  Refresh (analisis ulang)")
        console.print("[bold cyan]  S[/]  Ganti simbol")
        console.print("[bold cyan]  M[/]  Ganti mode trading (Scalping/Intraday/Swing)")
        console.print("[bold red]  0[/]  Kembali ke Menu Utama")
        hr()
        choice = ask("Pilih aksi", default="0").upper()
        if choice == "0":
            return
        elif choice == "R":
            continue
        elif choice == "S":
            symbol = ""
        elif choice == "M":
            console.print()
            for m in config.TRADING_MODES:
                console.print(f"  [bold cyan]{m['id']}[/]  {m['code']:<10} {' / '.join(m['timeframes'])}")
                console.print(f"       [dim]{m['desc']}[/]")
            pick = ask_int("Pilih mode trading (1-3)", default=mode["id"])
            if pick and 1 <= pick <= 3:
                settings["trading_mode"] = config.TRADING_MODES[pick - 1]["code"]
                config.save_settings(settings)
                success(f"Mode trading: {settings['trading_mode']}")
            else:
                warn("Pilihan tidak valid (harus 1-3).")
            press_enter()
        else:
            warn("Pilihan tidak valid.")
            press_enter()


# ===========================================================================
# MENU 2 — PENGATURAN TRADE
# ===========================================================================
def trade_settings_menu() -> None:
    settings = config.load_settings()
    while True:
        banner("MENU 2 — PENGATURAN TRADE")
        console.print(settings_table(settings))
        hr()
        console.print("[bold cyan]  1[/]  Ubah Risk : Reward (contoh: 1:2, 1:3)")
        console.print("[bold cyan]  2[/]  Ubah Metode Analisis (pilih 1-5)")
        console.print("[bold cyan]  3[/]  Ubah Target Pips")
        console.print("[bold cyan]  4[/]  Ubah Mode Trading (Scalping/Intraday/Swing)")
        console.print("[bold green]  S[/]  Simpan")
        console.print("[bold red]  0[/]  Kembali ke Menu Utama")
        hr()
        choice = ask("Pilih", default="0").upper()

        if choice == "0":
            return
        elif choice == "1":
            settings["risk_reward"] = ask("Risk : Reward", default=settings["risk_reward"],
                                          allow_empty=False)
        elif choice == "2":
            console.print()
            for m in config.ANALYSIS_METHODS:
                console.print(f"  [bold cyan]{m['id']}[/]  {m['code']:<10} {m['name']}")
                console.print(f"       [dim]{m['desc']}[/]")
            pick = ask_int("Pilih metode (1-5)", default=None)
            if pick and 1 <= pick <= 5:
                settings["analysis_method"] = config.ANALYSIS_METHODS[pick - 1]["code"]
                success(f"Metode dipilih: {settings['analysis_method']}")
            else:
                warn("Pilihan tidak valid (harus 1-5).")
            press_enter()
        elif choice == "3":
            val = ask_int("Target pips", default=settings["target_pips"])
            if val is not None and val > 0:
                settings["target_pips"] = val
        elif choice == "4":
            console.print()
            for m in config.TRADING_MODES:
                console.print(f"  [bold cyan]{m['id']}[/]  {m['code']:<10} {' / '.join(m['timeframes'])}")
                console.print(f"       [dim]{m['desc']}[/]")
            cur = config.trading_mode_by_code(settings.get("trading_mode", "Intraday"))
            pick = ask_int("Pilih mode trading (1-3)", default=cur["id"] if cur else 2)
            if pick and 1 <= pick <= 3:
                settings["trading_mode"] = config.TRADING_MODES[pick - 1]["code"]
                success(f"Mode trading: {settings['trading_mode']}")
            else:
                warn("Pilihan tidak valid (harus 1-3).")
            press_enter()
        elif choice == "S":
            config.save_settings(settings)
            success("Pengaturan trade tersimpan.")
            press_enter()
        else:
            warn("Pilihan tidak valid.")
            press_enter()


# ===========================================================================
# MENU 3 — ENV (API KEY & URL)
# ===========================================================================
def env_menu() -> None:
    while True:
        banner("MENU 3 — ENV (API KEY & URL)")
        config.load_env()
        rows = []
        for var, label, url, secret in ENV_EDITABLE:
            val = config.env(var)
            display = mask_secret(val) if secret else (val or "[dim](default kosong)[/]")
            rows.append((var, display, f"{label} • {url}"))
        console.print(env_table(rows))
        hr()
        console.print("[dim]Ketik nomor (1-7) untuk mengedit variabel tersebut.[/]")
        console.print("[bold green]  S[/]  Simpan & refresh")
        console.print("[bold red]  0[/]  Kembali ke Menu Utama")
        hr()
        choice = ask("Pilih", default="0").upper()

        if choice == "0":
            return
        if choice == "S":
            config.load_env()
            success("Konfigurasi .env dimuat ulang.")
            press_enter()
            continue

        try:
            idx = int(choice) - 1
        except ValueError:
            warn("Pilihan tidak valid.")
            press_enter()
            continue
        if not (0 <= idx < len(ENV_EDITABLE)):
            warn("Nomor di luar rentang (1-7).")
            press_enter()
            continue

        var, label, url, secret = ENV_EDITABLE[idx]
        current = config.env(var)
        console.print(f"\n[cyan]{label}[/]")
        console.print(f"[dim]{url}[/]")
        if secret and current:
            console.print(f"Saat ini: {mask_secret(current)}")
        new_val = ask("Nilai baru (kosongkan untuk mempertahankan)", default=current)
        set_key(str(config.ENV_PATH), var, new_val, quote_mode="never")
        config.load_env()
        success(f"{var} tersimpan di .env")
        press_enter()
