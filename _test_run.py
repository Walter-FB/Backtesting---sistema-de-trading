"""
_test_run.py — Runner multi-activo para backtest masivo
========================================================
Descubre automáticamente todos los archivos *_1D_*.json en Data_Leo/,
ejecuta un TradingEngine independiente por cada uno (con su output
individual completo e intacto) y al final imprime un reporte acumulado
con las métricas combinadas de TODOS los activos.

Filosofía:
  - Cada engine corre aislado (balance propio, buffer propio).
  - Los TradeRecord de todos los runs se acumulan para el reporte final.
  - El drawdown acumulado se calcula sobre la curva de equity COMBINADA
    (concatenación de curvas individuales, sin resetear el capital).
  - No se modifica ningún otro módulo del sistema.
"""

import glob
import os
from datetime import datetime

from data_loader import JSONDataLoader
from engine import TradingEngine
from strategy_factory import StrategyFactory

# ── Colores ANSI ──────────────────────────────────────────────────────────────
_R   = "\033[0m"
_B   = "\033[1m"
_DIM = "\033[2m"
_G   = "\033[92m"
_Y   = "\033[93m"
_RED = "\033[91m"
_C   = "\033[96m"

# ── Configuración ─────────────────────────────────────────────────────────────
INITIAL_BALANCE: float = 100_000.0
DATA_DIR: str = os.path.join(os.path.dirname(__file__), "Data_Leo")
JSON_GLOB: str = os.path.join(DATA_DIR, "**", "*_1D_*.json")

# ── Estrategia activa ──────────────────────────────────────────────────────────
# Cambiá este string para probar otra estrategia. Opciones disponibles:
#   "connors_rsi2"       → Reversión a la media, opera en RANGING
#   "momentum_breakout"  → Seguimiento de tendencia, opera en TRENDING_BULLISH
STRATEGY_NAME: str = "ema_crossover"

# ESTRATEGIAS: "momentum_breakout" -  "ema_crossover"
# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE REPORTE ACUMULADO
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_max_drawdown(equity_curve: list) -> float:
    """Drawdown máximo sobre una curva de equity combinada."""
    if len(equity_curve) < 2:
        return 0.0
    peak   = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _print_combined_report(
    all_trades:   list,
    equity_curve: list,
    initial_balance: float,
    tickers_run:  list,
) -> None:
    """Imprime el reporte acumulado de todos los backtests."""

    print(f"\n{'═'*65}")
    print(f"  {_B}📊 REPORTE ACUMULADO — TODOS LOS ACTIVOS{_R}")
    print(f"  {_DIM}{len(tickers_run)} tickers: {', '.join(tickers_run)}{_R}")
    print(f"{'═'*65}")

    if not all_trades:
        print(f"  {_Y}Sin trades registrados en ningún activo.{_R}\n")
        return

    total   = len(all_trades)
    winners = [t for t in all_trades if t.pnl_net > 0]
    losers  = [t for t in all_trades if t.pnl_net <= 0]

    win_pct  = len(winners) / total
    loss_pct = len(losers)  / total

    avg_win_r  = (sum(t.r_multiple for t in winners) / len(winners)) if winners else 0.0
    avg_loss_r = abs(sum(t.r_multiple for t in losers) / len(losers)) if losers else 0.0
    expectancy = (win_pct * avg_win_r) - (loss_pct * avg_loss_r)

    total_pnl    = sum(t.pnl_net for t in all_trades)
    total_return = (total_pnl / (initial_balance * len(tickers_run))) * 100
    max_dd       = _compute_max_drawdown(equity_curve)

    pnl_col  = _G   if total_pnl  >= 0 else _RED
    exp_col  = _G   if expectancy >= 0 else _RED
    pnl_sign = "+"  if total_pnl  >= 0 else ""
    exp_sign = "+"  if expectancy >= 0 else ""

    # ── Performance general ────────────────────────────────────────────────────
    print(f"\n  {_B}PERFORMANCE GENERAL{_R}")
    print(f"  {'─'*40}")
    print(f"  Capital por activo : {_B}${initial_balance:>12,.2f}{_R}")
    print(f"  PnL neto total     : {pnl_col}{_B}${pnl_sign}{total_pnl:>11,.2f}{_R}")
    print(f"  Retorno total      : {pnl_col}{_B}{pnl_sign}{total_return:>9.2f}%{_R}")
    print(f"  Max Drawdown       : {_RED}{max_dd:>10.2f}%{_R}")

    # ── Estadísticas de trades ─────────────────────────────────────────────────
    print(f"\n  {_B}ESTADÍSTICAS DE TRADES{_R}")
    print(f"  {'─'*40}")
    print(f"  Total trades       : {_B}{total:>10d}{_R}")
    print(f"  Ganadores          : {_G}{len(winners):>10d}{_R}")
    print(f"  Perdedores         : {_RED}{len(losers):>10d}{_R}")
    print(f"  Win Rate           : {_B}{win_pct*100:>10.1f}%{_R}")

    # ── R-múltiplos ────────────────────────────────────────────────────────────
    print(f"\n  {_B}R-MÚLTIPLOS (Esperanza Matemática){_R}")
    print(f"  {'─'*40}")
    print(f"  Avg Win  (R)       : {_G}{avg_win_r:>10.3f}R{_R}")
    print(f"  Avg Loss (R)       : {_RED}{avg_loss_r:>10.3f}R{_R}")
    print(f"  Expectancy         : {exp_col}{_B}{exp_sign}{expectancy:>9.3f}R{_R}")

    # ── Razones de salida ──────────────────────────────────────────────────────
    reasons: dict = {}
    for t in all_trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

    print(f"\n  {_B}RAZONES DE SALIDA{_R}")
    print(f"  {'─'*40}")
    for reason, count in sorted(reasons.items()):
        pct = count / total * 100
        col = _G if reason == "RSI_TARGET" else _Y if reason == "TIME_STOP" else _DIM
        print(f"  {col}{reason:<20}{_R}: {count:>4d}  ({pct:.1f}%)")

    # ── Trades destacados ──────────────────────────────────────────────────────
    best_trade  = max(all_trades, key=lambda t: t.pnl_net)
    worst_trade = min(all_trades, key=lambda t: t.pnl_net)

    print(f"\n  {_B}TRADES DESTACADOS{_R}")
    print(f"  {'─'*40}")
    print(f"  Mayor ganancia : {_G}{_B}${best_trade.pnl_net:>+11,.2f}{_R}  [{best_trade.ticker:<6}  {best_trade.exit_reason}]")
    print(f"  Mayor pérdida  : {_RED}{_B}${worst_trade.pnl_net:>+11,.2f}{_R}  [{worst_trade.ticker:<6}  {worst_trade.exit_reason}]")

    # Avg PnL por razón de salida
    by_reason: dict = {}
    for t in all_trades:
        by_reason.setdefault(t.exit_reason, []).append(t)

    print(f"\n  {_B}ANÁLISIS POR RAZÓN DE SALIDA{_R}")
    print(f"  {'─'*40}")
    print(f"  {'Razón':<24} {'N':>4}  {'Avg PnL $':>11}  {'Avg R':>7}  {'Mejor':>10}  {'Peor':>10}")
    print(f"  {'─'*24} {'─'*4}  {'─'*11}  {'─'*7}  {'─'*10}  {'─'*10}")
    for reason, trades_r in sorted(by_reason.items()):
        avg_pnl = sum(t.pnl_net for t in trades_r) / len(trades_r)
        avg_r   = sum(t.r_multiple for t in trades_r) / len(trades_r)
        best_r  = max(t.pnl_net for t in trades_r)
        worst_r = min(t.pnl_net for t in trades_r)
        col_p   = _G if avg_pnl >= 0 else _RED
        col_r   = _G if avg_r   >= 0 else _RED
        ps_avg  = "+" if avg_pnl >= 0 else ""
        ps_r    = "+" if avg_r   >= 0 else ""
        print(
            f"  {reason:<24} {len(trades_r):>4}  "
            f"{col_p}${ps_avg}{avg_pnl:>9,.2f}{_R}  "
            f"{col_r}{ps_r}{avg_r:>6.3f}R{_R}  "
            f"{_G}${best_r:>+9,.2f}{_R}  "
            f"{_RED}${worst_r:>+9,.2f}{_R}"
        )

    # ── Breakdown por ticker ───────────────────────────────────────────────────
    print(f"\n  {_B}BREAKDOWN POR TICKER{_R}")
    print(f"  {'─'*40}")
    by_ticker: dict = {}
    for t in all_trades:
        by_ticker.setdefault(t.ticker, []).append(t)
    for tkr, trades in sorted(by_ticker.items()):
        w   = sum(1 for t in trades if t.pnl_net > 0)
        wr  = w / len(trades) * 100
        pnl = sum(t.pnl_net for t in trades)
        pnl_s = "+" if pnl >= 0 else ""
        col   = _G if pnl >= 0 else _RED
        print(
            f"  {_B}{tkr:<8}{_R}  trades={len(trades):>3}  "
            f"WR={wr:>5.1f}%  PnL={col}{pnl_s}${pnl:>9,.2f}{_R}"
        )

    print(f"\n{'═'*65}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# GUARDADO DEL REPORTE ACUMULADO
# ═══════════════════════════════════════════════════════════════════════════════

def _build_txt_block(
    all_trades:   list,
    equity_curve: list,
    initial_balance: float,
    tickers_run:  list,
) -> str:
    """
    Construye el bloque de texto plano (sin ANSI) del reporte acumulado.
    Retorna el string listo para escribir al archivo.
    """
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    w65  = "=" * 65
    w40  = "-" * 40

    lines = []
    lines.append(w65)
    lines.append(f"  BACKTEST REPORT ACUMULADO — {STRATEGY_NAME}")
    lines.append(f"  Generado : {now}")
    lines.append(f"  Tickers  : {', '.join(tickers_run)}")
    lines.append(w65)

    if not all_trades:
        lines.append("  Sin trades registrados en ningún activo.")
        lines.append("")
        return "\n".join(lines)

    total   = len(all_trades)
    winners = [t for t in all_trades if t.pnl_net > 0]
    losers  = [t for t in all_trades if t.pnl_net <= 0]
    win_pct  = len(winners) / total
    loss_pct = len(losers)  / total
    avg_win_r  = (sum(t.r_multiple for t in winners) / len(winners)) if winners else 0.0
    avg_loss_r = abs(sum(t.r_multiple for t in losers) / len(losers)) if losers else 0.0
    expectancy = (win_pct * avg_win_r) - (loss_pct * avg_loss_r)
    total_pnl    = sum(t.pnl_net for t in all_trades)
    total_return = (total_pnl / (initial_balance * len(tickers_run))) * 100 if tickers_run else 0.0
    max_dd       = _compute_max_drawdown(equity_curve)

    pnl_sign = "+" if total_pnl  >= 0 else ""
    exp_sign = "+" if expectancy >= 0 else ""

    lines.append("")
    lines.append("  PERFORMANCE GENERAL")
    lines.append("  " + w40)
    lines.append(f"  Capital por activo : ${initial_balance:>12,.2f}")
    lines.append(f"  PnL neto total     : ${pnl_sign}{total_pnl:>11,.2f}")
    lines.append(f"  Retorno total      : {pnl_sign}{total_return:>10.2f}%")
    lines.append(f"  Max Drawdown       :  {max_dd:>10.2f}%")

    lines.append("")
    lines.append("  ESTADÍSTICAS DE TRADES")
    lines.append("  " + w40)
    lines.append(f"  Total trades       : {total:>10d}")
    lines.append(f"  Ganadores          : {len(winners):>10d}")
    lines.append(f"  Perdedores         : {len(losers):>10d}")
    lines.append(f"  Win Rate           : {win_pct*100:>10.1f}%")

    lines.append("")
    lines.append("  R-MÚLTIPLOS (Esperanza Matemática)")
    lines.append("  " + w40)
    lines.append(f"  Avg Win  (R)       : {avg_win_r:>10.3f}R")
    lines.append(f"  Avg Loss (R)       : {avg_loss_r:>10.3f}R")
    lines.append(f"  Expectancy         : {exp_sign}{expectancy:>9.3f}R")

    # Trades destacados
    best_trade  = max(all_trades, key=lambda t: t.pnl_net)
    worst_trade = min(all_trades, key=lambda t: t.pnl_net)

    lines.append("")
    lines.append("  TRADES DESTACADOS")
    lines.append("  " + w40)
    lines.append(f"  Mayor ganancia : ${best_trade.pnl_net:>+11,.2f}  [{best_trade.ticker:<6}  {best_trade.exit_reason}]")
    lines.append(f"  Mayor pérdida  : ${worst_trade.pnl_net:>+11,.2f}  [{worst_trade.ticker:<6}  {worst_trade.exit_reason}]")

    by_reason: dict = {}
    for t in all_trades:
        by_reason.setdefault(t.exit_reason, []).append(t)

    lines.append("")
    lines.append("  ANÁLISIS POR RAZÓN DE SALIDA")
    lines.append("  " + w40)
    lines.append(f"  {'Razón':<24} {'N':>4}  {'Avg PnL $':>11}  {'Avg R':>7}  {'Mejor':>10}  {'Peor':>10}")
    lines.append(f"  {'-'*24} {'-'*4}  {'-'*11}  {'-'*7}  {'-'*10}  {'-'*10}")
    for reason, trades_r in sorted(by_reason.items()):
        avg_pnl = sum(t.pnl_net for t in trades_r) / len(trades_r)
        avg_r   = sum(t.r_multiple for t in trades_r) / len(trades_r)
        best_r  = max(t.pnl_net for t in trades_r)
        worst_r = min(t.pnl_net for t in trades_r)
        ps_avg  = "+" if avg_pnl >= 0 else ""
        ps_r    = "+" if avg_r   >= 0 else ""
        lines.append(
            f"  {reason:<24} {len(trades_r):>4}  "
            f"${ps_avg}{avg_pnl:>9,.2f}  "
            f"{ps_r}{avg_r:>6.3f}R  "
            f"${best_r:>+9,.2f}  "
            f"${worst_r:>+9,.2f}"
        )

    reasons: dict = {}
    for t in all_trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

    lines.append("")
    lines.append("  RAZONES DE SALIDA")
    lines.append("  " + w40)
    for reason, count in sorted(reasons.items()):
        pct = count / total * 100
        lines.append(f"  {reason:<20}: {count:>4d}  ({pct:.1f}%)")

    by_ticker: dict = {}
    for t in all_trades:
        by_ticker.setdefault(t.ticker, []).append(t)

    lines.append("")
    lines.append("  BREAKDOWN POR TICKER")
    lines.append("  " + w40)
    for tkr, trades in sorted(by_ticker.items()):
        w   = sum(1 for t in trades if t.pnl_net > 0)
        wr  = w / len(trades) * 100
        pnl = sum(t.pnl_net for t in trades)
        ps  = "+" if pnl >= 0 else ""
        lines.append(
            f"  {tkr:<8}  trades={len(trades):>3}  "
            f"WR={wr:>5.1f}%  PnL={ps}${pnl:>9,.2f}"
        )

    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _save_combined_report(
    all_trades:   list,
    equity_curve: list,
    initial_balance: float,
    tickers_run:  list,
    output_dir:   str = ".",
) -> str:
    """
    Guarda el reporte acumulado en backtest_report.txt PREPENDÁNDOLO
    al contenido anterior: el más reciente queda siempre al principio.
    """
    path = os.path.join(output_dir, "backtest_report.txt")

    # Leer contenido existente (si hay)
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()

    nuevo = _build_txt_block(all_trades, equity_curve, initial_balance, tickers_run)

    with open(path, "w", encoding="utf-8") as f:
        f.write(nuevo)
        if existing.strip():
            f.write(existing)

    return path


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    loader = JSONDataLoader()

    # Descubrir todos los JSONs 1D
    json_files = sorted(glob.glob(JSON_GLOB, recursive=True))

    if not json_files:
        print(f"{_RED}No se encontraron archivos *_1D_*.json en {DATA_DIR}{_R}")
        return

    # Acumuladores para el reporte final
    all_trades:   list = []
    equity_curve: list = []
    tickers_run:  list = []

    for json_path in json_files:
        # Extraer ticker del nombre de archivo: "COST_1D_3000Bars.json" → "COST"
        fname  = os.path.basename(json_path)
        ticker = fname.split("_")[0]

        candles = loader.load_from_json(json_path)

        engine = TradingEngine(
            strategy       = StrategyFactory.create(STRATEGY_NAME),
            initial_balance= INITIAL_BALANCE,
        )

        # Silenciar los saves individuales: el engine llama a save_csv() y
        # save_txt() al final de cada run, sobreescribiendo el archivo.
        # Los reemplazamos con no-ops en la instancia; el output de terminal
        # individual queda intacto.
        engine.tracker.save_csv = lambda filename="": ""
        engine.tracker.save_txt = lambda initial_balance=0, ticker="", filename="": ""

        engine.run_backtest(candles, ticker=ticker)

        # Acumular trades y curva de equity de este run
        all_trades.extend(engine.tracker.trades)
        equity_curve.extend(engine.tracker._equity_curve)
        tickers_run.append(ticker)

    # Reporte final acumulado
    _print_combined_report(
        all_trades      = all_trades,
        equity_curve    = equity_curve,
        initial_balance = INITIAL_BALANCE,
        tickers_run     = tickers_run,
    )

    txt_path = _save_combined_report(
        all_trades      = all_trades,
        equity_curve    = equity_curve,
        initial_balance = INITIAL_BALANCE,
        tickers_run     = tickers_run,
        output_dir      = os.path.dirname(os.path.abspath(__file__)),
    )
    import logging
    logging.getLogger(__name__).info(f"Reporte acumulado guardado: {txt_path}")


if __name__ == "__main__":
    main()
