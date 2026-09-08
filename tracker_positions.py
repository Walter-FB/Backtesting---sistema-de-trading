"""
tracker_positions.py — Registro y Seguimiento de Operaciones
============================================================
Gestiona el ciclo de vida completo de cada operación del backtest.

Componentes:
  Position     : Estado de una posición actualmente abierta.
                 Se crea al entrar y se destruye al salir.
  TradeRecord  : Snapshot inmutable de una operación cerrada.
                 Contiene todos los datos para análisis posterior.
  TradeTracker : Motor de registro y análisis.
                 - Almacena todos los TradeRecord cerrados
                 - Trackea la curva de equity para calcular drawdown
                 - Genera reporte CSV, TXT y print en terminal

Flujo:
  engine.py crea un Position al entrar → lo pasa a record_trade() al salir
  → TradeTracker lo convierte en TradeRecord y lo guarda
  → Al final del backtest, TradeTracker genera los reportes
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


# ── Constante de comisión (importada por engine.py también) ──────────────────
COMMISSION_PCT: float = 0.001   # 0.1% del valor de la operación, por lado


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    """
    Estado de una posición actualmente abierta.

    Se crea en el engine cuando se ejecuta una entrada.
    Se destruye cuando se cierra el trade (pasando a TradeRecord).

    Campos
    ------
    ticker       : str   — símbolo del activo (ej: "COST")
    entry_date   : str   — fecha de entrada en formato "YYYY-MM-DD"
    entry_price  : float — precio de apertura del día de entrada
    quantity     : float — cantidad de acciones/unidades compradas
    risk_amount  : float — capital × risk_pct al momento de la señal ($)
    atr_at_entry : float — ATR(14) en la vela de señal (referencia)
    candles_held : int   — velas transcurridas desde la entrada (contador)
    """
    ticker:           str
    entry_date:       str
    entry_price:      float
    quantity:         float
    risk_amount:      float
    atr_at_entry:     float
    candles_held:     int = 0    # se incrementa cada vela en el loop del engine
    climate_at_entry: str = ""   # label del ClimateReading vigente al momento de la señal


@dataclass
class TradeRecord:
    """
    Registro completo e inmutable de una operación cerrada.

    Se almacena en memoria y se guarda en CSV/TXT al final del backtest.

    Campos calculados por TradeTracker.record_trade()
    --------------------------------------------------
    pnl_gross   : ganancia/pérdida sin considerar comisiones
    pnl_net     : ganancia/pérdida neta (después de comm. de entrada y salida)
    pnl_pct     : retorno porcentual sobre el capital invertido bruto
    commission  : costo total de comisiones (entrada + salida)
    r_multiple  : pnl_net / risk_amount — cuántos "R" ganó o perdió el trade

    exit_reason puede ser:
      "RSI_TARGET"   : RSI(2) cruzó por encima de 50 (objetivo alcanzado)
      "TIME_STOP"    : 10 velas elapsed sin alcanzar el target
      "FIN_BACKTEST" : posición forzosamente cerrada al terminar los datos
    """
    ticker:        str
    entry_date:    str
    exit_date:     str
    entry_price:   float
    exit_price:    float
    quantity:      float
    commission:    float
    pnl_gross:     float
    pnl_net:       float
    pnl_pct:       float
    exit_reason:   str
    r_multiple:    float
    balance_after: float
    climate_label: str = ""   # clima vigente al momento de la entrada (ver Position.climate_at_entry)


# ═══════════════════════════════════════════════════════════════════════════════
# TRADE TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

class TradeTracker:
    """
    Motor de registro, análisis y reporte del backtest.

    Responsabilidades:
      1. Almacenar cada trade cerrado en memoria (lista de TradeRecord)
      2. Calcular métricas de performance (win rate, expectancy, drawdown)
      3. Generar archivo CSV con el historial detallado de trades
      4. Generar archivo TXT con el reporte de performance completo
      5. Imprimir resumen en terminal con colores ANSI

    Atributos públicos
    ------------------
    trades : List[TradeRecord] — todos los trades cerrados

    Métodos públicos
    ----------------
    update_equity(balance)                      → actualiza la curva de equity
    record_trade(position, exit_price, ...)     → cierra un trade, devuelve TradeRecord
    get_performance(initial_balance)            → dict con métricas de performance
    save_csv(filename)                          → guarda CSV, retorna ruta
    save_txt(filename, initial_balance)         → guarda TXT, retorna ruta
    print_report(initial_balance)               → imprime reporte en terminal
    """

    def __init__(self, output_dir: str = ".") -> None:
        self.trades:       List[TradeRecord] = []
        self.output_dir:   str               = output_dir

        # Estado interno para drawdown
        self._peak_balance: float       = 0.0
        self._equity_curve: List[float] = []

    # ── Actualización de equity ───────────────────────────────────────────────

    def update_equity(self, balance: float) -> None:
        """
        Registra el balance actual en la curva de equity.
        Debe llamarse en CADA vela del loop del backtest para un drawdown preciso.

        Parámetros
        ----------
        balance : float — balance actual de la cuenta (después de cualquier trade)
        """
        self._equity_curve.append(balance)
        if balance > self._peak_balance:
            self._peak_balance = balance

    # ── Registro de trade cerrado ─────────────────────────────────────────────

    def record_trade(
        self,
        position:      Position,
        exit_price:    float,
        exit_date:     str,
        exit_reason:   str,
        balance_after: float,
    ) -> TradeRecord:
        """
        Cierra una posición abierta y guarda el TradeRecord resultante.

        Parámetros
        ----------
        position      : Position — posición que se está cerrando
        exit_price    : float    — precio de ejecución de la salida (open del día siguiente)
        exit_date     : str      — fecha de salida ("YYYY-MM-DD")
        exit_reason   : str      — razón de salida ("RSI_TARGET"|"TIME_STOP"|"FIN_BACKTEST")
        balance_after : float    — balance de la cuenta DESPUÉS de registrar el trade

        Retorna
        -------
        TradeRecord — snapshot completo del trade cerrado (ya guardado en self.trades)
        """
        # ── Cálculo de valores brutos ─────────────────────────────────────────
        gross_entry = position.entry_price * position.quantity
        gross_exit  = exit_price           * position.quantity

        # Comisión de 0.1% sobre cada lado
        comm_entry = gross_entry * COMMISSION_PCT
        comm_exit  = gross_exit  * COMMISSION_PCT
        commission = comm_entry + comm_exit

        # P&L
        pnl_gross = gross_exit  - gross_entry
        pnl_net   = pnl_gross   - commission

        # Retorno porcentual sobre el capital invertido (base bruta)
        pnl_pct = (pnl_net / gross_entry) * 100 if gross_entry > 0 else 0.0

        # R-múltiplo: cuántos veces el riesgo inicial se ganó o perdió
        r_multiple = pnl_net / position.risk_amount if position.risk_amount > 0 else 0.0

        record = TradeRecord(
            ticker        = position.ticker,
            entry_date    = position.entry_date,
            exit_date     = exit_date,
            entry_price   = position.entry_price,
            exit_price    = exit_price,
            quantity      = position.quantity,
            commission    = commission,
            pnl_gross     = pnl_gross,
            pnl_net       = pnl_net,
            pnl_pct       = pnl_pct,
            exit_reason   = exit_reason,
            r_multiple    = r_multiple,
            balance_after = balance_after,
            climate_label = position.climate_at_entry,
        )

        self.trades.append(record)
        return record

    # ── Métricas de performance ───────────────────────────────────────────────

    def get_performance(self, initial_balance: float) -> dict:
        """
        Calcula todas las métricas de performance del backtest completo.

        Parámetros
        ----------
        initial_balance : float — capital inicial (para calcular retorno total %)

        Retorna
        -------
        dict con las siguientes claves:
          total_trades    : int   — cantidad total de trades
          winners         : int   — trades con PnL neto > 0
          losers          : int   — trades con PnL neto ≤ 0
          win_rate        : float — % de trades ganadores (0–100)
          avg_win_r       : float — R-múltiplo promedio de los trades ganadores
          avg_loss_r      : float — R-múltiplo promedio (abs) de los perdedores
          expectancy      : float — (Win% × AvgWinR) − (Loss% × AvgLossR)
          total_pnl       : float — suma de todos los PnL netos ($)
          total_return_pct: float — retorno total sobre el capital inicial (%)
          max_drawdown_pct: float — caída máxima de la curva de equity (%)
        """
        if not self.trades:
            return {}

        total    = len(self.trades)
        winners  = [t for t in self.trades if t.pnl_net > 0]
        losers   = [t for t in self.trades if t.pnl_net <= 0]

        win_pct  = len(winners) / total
        loss_pct = len(losers)  / total

        avg_win_r  = (sum(t.r_multiple for t in winners) / len(winners)) if winners else 0.0
        avg_loss_r = abs(sum(t.r_multiple for t in losers) / len(losers)) if losers else 0.0

        # Expectancy: esperanza matemática en unidades de R
        expectancy = (win_pct * avg_win_r) - (loss_pct * avg_loss_r)

        total_pnl    = sum(t.pnl_net for t in self.trades)
        total_return = (total_pnl / initial_balance) * 100

        return {
            "total_trades":     total,
            "winners":          len(winners),
            "losers":           len(losers),
            "win_rate":         win_pct * 100,
            "avg_win_r":        avg_win_r,
            "avg_loss_r":       avg_loss_r,
            "expectancy":       expectancy,
            "total_pnl":        total_pnl,
            "total_return_pct": total_return,
            "max_drawdown_pct": self._compute_max_drawdown(),
            "by_climate":       self._compute_breakdown_by_climate(),
        }

    def _compute_breakdown_by_climate(self) -> dict:
        """
        Agrupa los trades cerrados por el clima vigente al momento de la
        entrada (Position.climate_at_entry / TradeRecord.climate_label).

        Permite responder "¿en qué clima juega bien esta estrategia?" a
        partir de los resultados reales de backtest o paper trading, sin
        necesidad de declararlo de antemano.

        Retorna
        -------
        dict[str, dict] — una entrada por clima con:
          trades     : int   — cantidad de trades en ese clima
          win_rate   : float — % de trades ganadores dentro de ese clima
          total_pnl  : float — PnL neto acumulado en ese clima
          expectancy : float — esperanza matemática en R, dentro de ese clima
        """
        by_climate: dict = {}
        for t in self.trades:
            label = t.climate_label or "SIN_CLIMA"
            by_climate.setdefault(label, []).append(t)

        breakdown: dict = {}
        for label, trades in by_climate.items():
            total = len(trades)
            winners = [t for t in trades if t.pnl_net > 0]
            losers = [t for t in trades if t.pnl_net <= 0]
            win_pct = len(winners) / total
            loss_pct = len(losers) / total
            avg_win_r = (sum(t.r_multiple for t in winners) / len(winners)) if winners else 0.0
            avg_loss_r = abs(sum(t.r_multiple for t in losers) / len(losers)) if losers else 0.0

            breakdown[label] = {
                "trades":     total,
                "win_rate":   win_pct * 100,
                "total_pnl":  sum(t.pnl_net for t in trades),
                "expectancy": (win_pct * avg_win_r) - (loss_pct * avg_loss_r),
            }

        return breakdown

    def _compute_max_drawdown(self) -> float:
        """
        Calcula el Maximum Drawdown de la curva de equity registrada.

        Algoritmo: recorre la curva, mantiene el pico máximo visto hasta ahora
        y calcula la caída porcentual desde ese pico en cada punto.

        Retorna
        -------
        float — drawdown máximo en % (valor positivo representa pérdida)
                Ejemplo: 15.3 significa una caída máxima del 15.3% desde un pico.
        """
        if len(self._equity_curve) < 2:
            return 0.0

        peak   = self._equity_curve[0]
        max_dd = 0.0

        for value in self._equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        return max_dd

    # ── Guardado de archivos ──────────────────────────────────────────────────

    def save_csv(self, filename: str = "trades_history.csv") -> str:
        """
        Guarda todos los trades cerrados en un archivo CSV.
        Una fila por trade, con todos los campos del TradeRecord.

        Parámetros
        ----------
        filename : str — nombre del archivo (se guarda en output_dir)

        Retorna
        -------
        str — ruta completa del archivo generado
        """
        path = os.path.join(self.output_dir, filename)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Encabezados
            writer.writerow([
                "N", "Ticker",
                "Fecha_Entrada", "Fecha_Salida",
                "Precio_Entrada", "Precio_Salida",
                "Cantidad", "Comision",
                "PnL_Bruto", "PnL_Neto", "PnL_Pct",
                "Exit_Reason", "R_Multiple", "Balance_Despues", "Clima_Entrada",
            ])
            for n, t in enumerate(self.trades, 1):
                writer.writerow([
                    n, t.ticker,
                    t.entry_date, t.exit_date,
                    f"{t.entry_price:.4f}", f"{t.exit_price:.4f}",
                    f"{t.quantity:.4f}",    f"{t.commission:.2f}",
                    f"{t.pnl_gross:.2f}",  f"{t.pnl_net:.2f}",
                    f"{t.pnl_pct:.2f}",    t.exit_reason,
                    f"{t.r_multiple:.3f}", f"{t.balance_after:.2f}",
                    t.climate_label,
                ])

        return path

    def save_txt(
        self,
        initial_balance: float,
        ticker: str = "",
        filename: str = "backtest_report.txt",
    ) -> str:
        """
        Guarda el reporte completo de performance en un archivo TXT.
        Incluye métricas generales, breakdown de salidas y detalle de cada trade.

        Parámetros
        ----------
        initial_balance : float — capital inicial del backtest
        ticker          : str   — símbolo del activo testeado (para el header)
        filename        : str   — nombre del archivo (se guarda en output_dir)

        Retorna
        -------
        str — ruta completa del archivo generado
        """
        path = os.path.join(self.output_dir, filename)
        perf = self.get_performance(initial_balance)
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 65 + "\n")
            f.write(f"  BACKTEST REPORT — Ticker: {ticker or 'N/A'}  |  Generado: {now}\n")
            f.write("=" * 65 + "\n\n")

            if not perf:
                f.write("  Sin trades registrados.\n")
                return path

            pnl_sign = "+" if perf["total_pnl"] >= 0 else ""

            f.write("  PERFORMANCE GENERAL\n")
            f.write("  " + "-" * 40 + "\n")
            f.write(f"  Capital inicial    : ${initial_balance:>12,.2f}\n")
            f.write(f"  PnL neto total     : ${pnl_sign}{perf['total_pnl']:>11,.2f}\n")
            f.write(f"  Retorno total      : {pnl_sign}{perf['total_return_pct']:>10.2f}%\n")
            f.write(f"  Max Drawdown       :  {perf['max_drawdown_pct']:>10.2f}%\n\n")

            f.write("  ESTADÍSTICAS DE TRADES\n")
            f.write("  " + "-" * 40 + "\n")
            f.write(f"  Total trades       : {perf['total_trades']:>10d}\n")
            f.write(f"  Ganadores          : {perf['winners']:>10d}\n")
            f.write(f"  Perdedores         : {perf['losers']:>10d}\n")
            f.write(f"  Win Rate           : {perf['win_rate']:>10.1f}%\n\n")

            f.write("  R-MÚLTIPLOS\n")
            f.write("  " + "-" * 40 + "\n")
            f.write(f"  Avg Win  (R)       : {perf['avg_win_r']:>10.3f}R\n")
            f.write(f"  Avg Loss (R)       : {perf['avg_loss_r']:>10.3f}R\n")
            exp_sign = "+" if perf["expectancy"] >= 0 else ""
            f.write(f"  Expectancy         : {exp_sign}{perf['expectancy']:>9.3f}R\n\n")

            # Breakdown por razón de salida
            reasons: dict = {}
            for t in self.trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

            f.write("  RAZONES DE SALIDA\n")
            f.write("  " + "-" * 40 + "\n")
            for reason, count in sorted(reasons.items()):
                pct = count / perf["total_trades"] * 100
                f.write(f"  {reason:<20}: {count:>4d}  ({pct:.1f}%)\n")

            # Rendimiento por clima — en qué clima juega bien esta estrategia
            f.write("\n  RENDIMIENTO POR CLIMA\n")
            f.write("  " + "-" * 40 + "\n")
            for label, stats in sorted(
                perf["by_climate"].items(), key=lambda kv: kv[1]["total_pnl"], reverse=True
            ):
                exp_sign = "+" if stats["expectancy"] >= 0 else ""
                pnl_sign = "+" if stats["total_pnl"] >= 0 else ""
                f.write(
                    f"  {label:<24}: {stats['trades']:>4d} trades  |  "
                    f"WR {stats['win_rate']:>5.1f}%  |  "
                    f"PnL {pnl_sign}${stats['total_pnl']:>9,.2f}  |  "
                    f"Exp {exp_sign}{stats['expectancy']:.3f}R\n"
                )

            # Detalle de trades
            f.write("\n  DETALLE DE TRADES\n")
            f.write("  " + "-" * 65 + "\n")
            f.write(
                f"  {'#':>4}  {'ENTRADA':>10}  {'SALIDA':>10}  "
                f"{'ENT$':>8}  {'SAL$':>8}  {'PnL$':>8}  {'R':>6}  RAZÓN\n"
            )
            f.write("  " + "-" * 65 + "\n")

            for n, t in enumerate(self.trades, 1):
                pnl_sign = "+" if t.pnl_net >= 0 else ""
                f.write(
                    f"  {n:>4}  {t.entry_date:>10}  {t.exit_date:>10}  "
                    f"${t.entry_price:>7.2f}  ${t.exit_price:>7.2f}  "
                    f"${pnl_sign}{t.pnl_net:>6.2f}  {t.r_multiple:>+5.2f}R  "
                    f"{t.exit_reason}\n"
                )

        return path

    # ── Reporte en terminal ───────────────────────────────────────────────────

    def print_report(self, initial_balance: float) -> None:
        """
        Imprime el reporte de performance en la terminal con colores ANSI.
        Incluye métricas generales, R-múltiplos y expectancy.

        Parámetros
        ----------
        initial_balance : float — capital inicial para calcular retorno total
        """
        # Colores ANSI (evitar dependencia de engine.py)
        _R   = "\033[0m"
        _B   = "\033[1m"
        _DIM = "\033[2m"
        _G   = "\033[92m"
        _Y   = "\033[93m"
        _RED = "\033[91m"
        _C   = "\033[96m"

        perf = self.get_performance(initial_balance)

        print(f"\n{_B}{'═'*65}{_R}")
        print(f"  {_B}📊 REPORTE FINAL DE PERFORMANCE{_R}")
        print(f"{_B}{'═'*65}{_R}")

        if not perf:
            print(f"  {_Y}Sin trades registrados en este backtest.{_R}")
            print(f"  {_DIM}(El activo puede no haber generado señales de entrada){_R}\n")
            return

        pnl_col = _G if perf["total_pnl"] >= 0 else _RED
        exp_col = _G if perf["expectancy"] >= 0 else _RED
        pnl_sign = "+" if perf["total_pnl"] >= 0 else ""
        exp_sign = "+" if perf["expectancy"] >= 0 else ""

        print(f"\n  {_B}PERFORMANCE GENERAL{_R}")
        print(f"  {'─'*40}")
        print(f"  Capital inicial    : {_B}${initial_balance:>12,.2f}{_R}")
        print(f"  PnL neto total     : {pnl_col}{_B}${pnl_sign}{perf['total_pnl']:>11,.2f}{_R}")
        print(f"  Retorno total      : {pnl_col}{_B}{pnl_sign}{perf['total_return_pct']:>9.2f}%{_R}")
        print(f"  Max Drawdown       : {_RED}{perf['max_drawdown_pct']:>10.2f}%{_R}")

        print(f"\n  {_B}ESTADÍSTICAS DE TRADES{_R}")
        print(f"  {'─'*40}")
        print(f"  Total trades       : {_B}{perf['total_trades']:>10d}{_R}")
        print(f"  Ganadores          : {_G}{perf['winners']:>10d}{_R}")
        print(f"  Perdedores         : {_RED}{perf['losers']:>10d}{_R}")
        print(f"  Win Rate           : {_B}{perf['win_rate']:>10.1f}%{_R}")

        print(f"\n  {_B}R-MÚLTIPLOS (Esperanza Matemática){_R}")
        print(f"  {'─'*40}")
        print(f"  Avg Win  (R)       : {_G}{perf['avg_win_r']:>10.3f}R{_R}")
        print(f"  Avg Loss (R)       : {_RED}{perf['avg_loss_r']:>10.3f}R{_R}")
        print(f"  Expectancy         : {exp_col}{_B}{exp_sign}{perf['expectancy']:>9.3f}R{_R}")

        # Breakdown por razón de salida
        reasons: dict = {}
        for t in self.trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

        print(f"\n  {_B}RAZONES DE SALIDA{_R}")
        print(f"  {'─'*40}")
        for reason, count in sorted(reasons.items()):
            pct = count / perf["total_trades"] * 100
            col = _G if reason == "RSI_TARGET" else _Y if reason == "TIME_STOP" else _DIM
            print(f"  {col}{reason:<20}{_R}: {count:>4d}  ({pct:.1f}%)")

        # Rendimiento por clima — en qué clima juega bien esta estrategia
        print(f"\n  {_B}🌤  RENDIMIENTO POR CLIMA{_R}")
        print(f"  {'─'*40}")
        for label, stats in sorted(
            perf["by_climate"].items(), key=lambda kv: kv[1]["total_pnl"], reverse=True
        ):
            pnl_col = _G if stats["total_pnl"] >= 0 else _RED
            exp_col = _G if stats["expectancy"] >= 0 else _RED
            pnl_sign = "+" if stats["total_pnl"] >= 0 else ""
            exp_sign = "+" if stats["expectancy"] >= 0 else ""
            print(
                f"  {_B}{label:<24}{_R}: {stats['trades']:>4d} trades  │  "
                f"WR {stats['win_rate']:>5.1f}%  │  "
                f"PnL {pnl_col}{pnl_sign}${stats['total_pnl']:>9,.2f}{_R}  │  "
                f"Exp {exp_col}{exp_sign}{stats['expectancy']:.3f}R{_R}"
            )

        print(f"\n  {_DIM}Archivos generados:{_R}")
        print(f"  {_DIM}  → trades_history.csv{_R}")
        print(f"  {_DIM}  → backtest_report.txt{_R}")
        print(f"{_B}{'═'*65}{_R}\n")
