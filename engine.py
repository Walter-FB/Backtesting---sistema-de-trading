"""
engine.py — Motor de Ejecución del Sistema de Trading Algorítmico
=================================================================
Implementa el TradingEngine con buffer circular FIFO (collections.deque)
para garantizar la ausencia de Look-Ahead Bias.

REGLA DE ORO
------------
En cada iteración `i`, el motor SÓLO puede "ver":
  - La vela actual: data[i]
  - Las hasta 249 velas anteriores: contenido del fifo_buffer al momento de llamar
No existe ningún acceso a data[i+1] o índices futuros en este archivo.

Responsabilidades de este archivo:
  - Gestionar el buffer FIFO (deque circular)
  - Orquestar el flujo: cargar vela → calcular → analizar → loguear → [estrategia]
  - Delegar TODO el análisis a pronostico_del_clima.py

Uso
---
    python engine.py
    -> Te pedirá elegir un activo de Data_Leo/ o ingresar una ruta manualmente.

    # O desde otro módulo:
    from data_loader import JSONDataLoader
    from engine import TradingEngine

    loader = JSONDataLoader()
    candles = loader.load_from_json("Data_Leo/NASDAQ_COST/COST_1D_3000Bars.json")
    engine = TradingEngine()
    engine.run_backtest(candles)
"""

import logging
import os
from collections import deque
from typing import List, Optional

from analysis import MarketRegime
from signal_provider import SignalProvider
from Strategys_Backtesting.connors_rsi2 import RiskManager
from data_loader import JSONDataLoader
from models import Candle
from pronostico_del_clima import RegimeDetector, compute_and_set_indicators
from tracker_positions import COMMISSION_PCT, Position, TradeTracker

# ── Configuración de logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
FIFO_MAX_LEN: int = 250   # Máximo de velas en el buffer circular
LOG_EVERY_N:  int = 100   # Frecuencia del log de progreso en consola

# ── Colores ANSI para la terminal ─────────────────────────────────────────────
# Compatibles con VS Code terminal y Windows Terminal
_R  = "\033[0m"       # Reset
_B  = "\033[1m"       # Bold
_DIM = "\033[2m"      # Dim
_GRAY   = "\033[90m"  # Gris (waiting)
_RED    = "\033[91m"  # Rojo (bajista / riesgo)
_GREEN  = "\033[92m"  # Verde (rango / operable)
_YELLOW = "\033[93m"  # Amarillo (cash / precaución)
_BLUE   = "\033[94m"  # Azul (tendencia)
_CYAN   = "\033[96m"  # Cian (alcista)
_WHITE  = "\033[97m"  # Blanco (neutro)

# Color por régimen
_REGIME_COLORS = {
    "RANGING_MEAN_REVERSION": _GREEN,
    "TRENDING_BULLISH":        _CYAN,
    "TRENDING_BEARISH":        _RED,
    "HIGH_VOLATILITY_CASH":    _YELLOW,
    "WAITING_FOR_DATA":        _GRAY,
}


# ═══════════════════════════════════════════════════════════════════════════════
# TRADING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class TradingEngine:
    """
    Motor de backtesting con buffer circular FIFO (anti look-ahead bias).

    Diseño: Patrón Strategy + Inyección de Dependencias
      El motor es agnóstico a la estrategia concreta.
      Acepta cualquier objeto que implemente SignalProvider.

    Módulos integrados:
      - pronostico_del_clima : cálculo de indicadores y detección de régimen
      - strategy (inyectado) : cualquier instancia de SignalProvider
      - tracker_positions    : registro de trades, reporte CSV/TXT/terminal

    Flujo por vela:
      1. Agregar vela al FIFO
      2. Calcular indicadores
      3. Detectar régimen
      4. Ejecutar entrada pendiente (al open de HOY)
      5. Ejecutar salida pendiente  (al open de HOY)
      6. Incrementar candles_held si hay posición
      7. Evaluar condiciones de entrada O salida (al cierre de HOY)
      8. Actualizar curva de equity
      9. Loguear progreso
    """

    def __init__(self, strategy: SignalProvider, initial_balance: float = 100_000.0) -> None:
        # ── Buffer circular ───────────────────────────────────────────────────
        self.fifo_buffer: deque = deque(maxlen=FIFO_MAX_LEN)
        self.balance:     float = initial_balance
        self._initial_balance: float = initial_balance

        # ── Módulo de análisis ────────────────────────────────────────────────
        self.regime_detector: RegimeDetector = RegimeDetector()
        self.current_regime:  MarketRegime   = MarketRegime.WAITING_FOR_DATA

        # ── Módulo de estrategia (inyectado) ──────────────────────────────────
        # El motor no sabe qué estrategia es — solo que cumple SignalProvider.
        self.strategy:     SignalProvider = strategy
        self.risk_manager: RiskManager  = RiskManager()

        # ── Módulo de tracking ────────────────────────────────────────────────
        self.tracker: TradeTracker = TradeTracker(output_dir=".")

        # ── Estado de posición y señales pendientes ───────────────────────────
        self.current_position: Optional[Position] = None
        self._pending_signal:  bool              = False
        self._pending_exit:    bool              = False
        self._pending_reason:  str               = ""
        self._signal_atr:      Optional[float]   = None
        self._signal_balance:  float             = 0.0

        logger.info(
            f"TradingEngine inicializado | "
            f"Estrategia: {type(strategy).__name__} | "
            f"Buffer FIFO maxlen={FIFO_MAX_LEN} | "
            f"Balance inicial: ${self.balance:,.2f} | "
            f"Comisión: {COMMISSION_PCT*100:.1f}% por lado"
        )

    # ── Backtest principal ────────────────────────────────────────────────────

    def run_backtest(self, data: List[Candle], ticker: str = "TICKER") -> None:
        """
        Recorre la lista de velas cronológicamente y ejecuta el loop completo:
        datos → análisis → estrategia → ejecución → registro.

        ┌──────────────────────────────────────────────────────────┐
        │  REGLA DE ORO — Sin look-ahead                           │
        │  Señal detectada al CIERRE de vela i.                    │
        │  Ejecución al OPEN de vela i+1 (simulación realista).    │
        └──────────────────────────────────────────────────────────┘

        Parámetros
        ----------
        data   : List[Candle] — velas ordenadas cronológicamente
        ticker : str          — símbolo del activo (para los reportes)
        """
        if not data:
            logger.warning("Lista de velas vacía. Backtest abortado.")
            return

        total = len(data)
        logger.info(f"Iniciando backtest sobre {total} velas — {ticker}")
        print(f"\n{_B}{'═'*72}{_R}")
        print(f"  {_B}⚡ SISTEMA DE TRADING — BACKTEST{_R}")
        print(f"  {_DIM}{ticker}  │  {total} velas  │  Buffer FIFO maxlen={FIFO_MAX_LEN}{_R}")
        print(f"  {_DIM}Estrategia: {type(self.strategy).__name__}  │  Comisión: {COMMISSION_PCT*100:.1f}% por lado{_R}")
        print(f"{_B}{'═'*72}{_R}\n")

        for i, candle in enumerate(data):

            # ── PASO 1: Agregar vela al FIFO ──────────────────────────────────
            self.fifo_buffer.append(candle)

            # ── PASO 2: Calcular indicadores desde el buffer ──────────────────
            compute_and_set_indicators(self.fifo_buffer)

            # ── PASO 3: Detectar régimen ───────────────────────────────────────
            self.current_regime = self.regime_detector.detect(self.fifo_buffer)

            # ── PASO 4: Ejecutar entrada pendiente al OPEN de HOY ────────────
            # La señal se detectó al cierre de AYER; hoy ejecutamos al open.
            if self._pending_signal and self.current_position is None:
                self._execute_entry(candle, ticker)
            self._pending_signal = False

            # ── PASO 5: Ejecutar salida pendiente al OPEN de HOY ─────────────
            # La condición de salida se detectó al cierre de AYER.
            if self._pending_exit and self.current_position is not None:
                self._execute_exit(candle, self._pending_reason)
            self._pending_exit   = False
            self._pending_reason = ""

            # ── PASO 6: Incrementar contador de velas en posición ────────────
            if self.current_position is not None:
                self.current_position.candles_held += 1

            # ── PASO 7: Evaluar condiciones de estrategia (al CIERRE de HOY) ─
            if self.current_position is None:
                # Sin posición: revisar si hay señal de entrada
                if self.strategy.check_entry(
                    self.fifo_buffer,
                    self.current_regime,
                    self.regime_detector.bullish_bias,
                ):
                    self._pending_signal = True
                    self._signal_atr     = candle.atr_14
                    self._signal_balance = self.balance
            else:
                # Con posición: revisar si hay señal de salida
                exit_reason = self.strategy.check_exit(
                    self.fifo_buffer,
                    self.current_position.candles_held,
                )
                if exit_reason:
                    self._pending_exit   = True
                    self._pending_reason = exit_reason

            # ── PASO 8: Actualizar curva de equity (cash + MtM de posición) ──
            # Si hay posición abierta, el equity real = cash + valor de las acciones
            # al precio de cierre de HOY. Sin esto, el drawdown sería artificialmente
            # alto por la caída del cash al comprar.
            equity = self.balance
            if self.current_position is not None:
                mtm = candle.close * self.current_position.quantity
                equity += mtm
            self.tracker.update_equity(equity)

            # ── PASO 9: Log de progreso ───────────────────────────────────────
            self._log_progress(i, candle, total)

        # ── Cierre forzado al terminar el backtest ────────────────────────────
        if self.current_position is not None:
            last = data[-1]
            self._execute_exit(last, "FIN_BACKTEST", use_close=True)
            logger.info("Posición forzada a cierre al finalizar el backtest.")

        # ── Resumen final ─────────────────────────────────────────────────────
        print(f"\n{_B}{'═'*72}{_R}")
        print(f"  {_B}✅ BACKTEST COMPLETADO{_R}  {_DIM}{total} velas procesadas — {ticker}{_R}")
        print(f"  {_B}💰 Balance final   : {_GREEN}${self.balance:>12,.2f}{_R}")
        pnl = self.balance - self._initial_balance
        pnl_pct = (pnl / self._initial_balance) * 100
        pnl_col = _GREEN if pnl >= 0 else _RED
        pnl_sign = "+" if pnl >= 0 else ""
        print(f"  {_B}📈 PnL neto        : {pnl_col}{pnl_sign}${pnl:>11,.2f}  ({pnl_sign}{pnl_pct:.2f}%){_R}")
        print(f"{_B}{'═'*72}{_R}\n")
        logger.info("Backtest finalizado.")

        # ── Reportes ──────────────────────────────────────────────────────────
        self.tracker.print_report(self._initial_balance)
        csv_path = self.tracker.save_csv("trades_history.csv")
        txt_path = self.tracker.save_txt(
            initial_balance=self._initial_balance,
            ticker=ticker,
            filename="backtest_report.txt",
        )
        logger.info(f"Reporte CSV guardado: {csv_path}")
        logger.info(f"Reporte TXT guardado: {txt_path}")

    # ── Ejecución de operaciones ──────────────────────────────────────────────

    def _execute_entry(self, candle: Candle, ticker: str) -> None:
        """
        Ejecuta la compra al precio de apertura de la vela actual.
        Usa el ATR y balance capturados en el momento de la señal.

        Parámetros
        ----------
        candle : Candle — vela del día de ejecución (su open es el precio)
        ticker : str    — símbolo del activo para el registro
        """
        qty  = self.risk_manager.compute_quantity(self._signal_balance, self._signal_atr)
        cost = candle.open * qty * (1 + COMMISSION_PCT)

        if qty <= 0 or cost > self.balance:
            return   # sin ATR o sin capital suficiente

        self.balance -= cost
        self.current_position = Position(
            ticker       = ticker,
            entry_date   = candle.formatted_date,
            entry_price  = candle.open,
            quantity     = qty,
            risk_amount  = self.risk_manager.compute_risk_amount(self._signal_balance),
            atr_at_entry = self._signal_atr or 0.0,
        )
        logger.info(
            f"ENTRADA | {candle.formatted_date} | {ticker} | "
            f"Open=${candle.open:.2f} | Qty={qty:.2f} | Costo=${cost:.2f}"
        )

    def _execute_exit(
        self,
        candle: Candle,
        reason: str,
        use_close: bool = False,
    ) -> None:
        """
        Ejecuta la venta al precio de apertura (o cierre si use_close=True).
        Actualiza el balance, registra el trade y limpia la posición.

        Parámetros
        ----------
        candle    : Candle — vela del día de ejecución
        reason    : str    — razón de salida para el registro
        use_close : bool   — usar close en vez de open (solo para FIN_BACKTEST)
        """
        if self.current_position is None:
            return

        exit_price = candle.close if use_close else candle.open
        proceeds   = exit_price * self.current_position.quantity * (1 - COMMISSION_PCT)
        self.balance += proceeds

        trade = self.tracker.record_trade(
            position      = self.current_position,
            exit_price    = exit_price,
            exit_date     = candle.formatted_date,
            exit_reason   = reason,
            balance_after = self.balance,
        )
        logger.info(
            f"SALIDA  | {candle.formatted_date} | {self.current_position.ticker} | "
            f"Exit=${exit_price:.2f} | PnL=${trade.pnl_net:+.2f} | "
            f"R={trade.r_multiple:+.2f} | Razón={reason}"
        )
        self.current_position = None

    # ── Logging de progreso ───────────────────────────────────────────────────

    def _log_progress(self, i: int, candle: Candle, total: int) -> None:
        """
        Imprime en consola el estado del sistema cada LOG_EVERY_N velas
        (y siempre en la primera y última vela), con colores ANSI.
        """
        is_first = (i == 0)
        is_last  = (i == total - 1)
        is_nth   = ((i + 1) % LOG_EVERY_N == 0)

        if not (is_first or is_last or is_nth):
            return

        # ── Valores numéricos ─────────────────────────────────────────────────
        rsi2_val   = candle.rsi_2
        rsi14_val  = candle.rsi
        adx_val    = candle.adx_14
        atr_val    = candle.atr_14
        ema200_val = candle.ema_200

        rsi2_str   = f"{rsi2_val:.1f}"   if rsi2_val   is not None else " N/A"
        rsi14_str  = f"{rsi14_val:.1f}"  if rsi14_val  is not None else " N/A"
        atr_str    = f"{atr_val:.2f}"    if atr_val    is not None else "N/A"
        adx_str    = f"{adx_val:.1f}"    if adx_val    is not None else "N/A"
        ema200_str = f"{ema200_val:.2f}" if ema200_val is not None else "N/A"

        # ── Color del RSI(2) según nivel ──────────────────────────────────────
        if rsi2_val is None:
            rsi2_col = _GRAY
        elif rsi2_val >= 90 or rsi2_val <= 10:
            rsi2_col = _RED     # extremo — señal fuerte
        elif rsi2_val >= 70 or rsi2_val <= 30:
            rsi2_col = _YELLOW  # zona de interés
        else:
            rsi2_col = _WHITE   # neutro

        # ── Color del ADX según nivel ─────────────────────────────────────────
        if adx_val is None:
            adx_col = _GRAY
        elif adx_val < 20:
            adx_col = _GREEN    # rango
        elif adx_val <= 25:
            adx_col = _YELLOW   # zona gris
        elif adx_val <= 40:
            adx_col = _CYAN     # tendencia
        else:
            adx_col = _RED      # agotamiento

        # ── Posición vs EMA200 ────────────────────────────────────────────────
        if ema200_val is not None:
            if candle.close > ema200_val:
                pos_str = f"{_GREEN}↑ SOBRE EMA200{_R}"
            else:
                pos_str = f"{_RED}↓ BAJO  EMA200{_R}"
        else:
            pos_str = f"{_GRAY}— sin EMA200  {_R}"

        # ── Régimen y sesgo ───────────────────────────────────────────────────
        regime_name = self.current_regime.name
        regime_col  = _REGIME_COLORS.get(regime_name, _WHITE)
        bias        = self.regime_detector.bullish_bias
        bias_str    = (
            f"{_GREEN}▲ ALCISTA{_R}" if bias is True
            else f"{_RED}▼ BAJISTA{_R}" if bias is False
            else f"{_GRAY}  N/A    {_R}"
        )

        buffer_size = len(self.fifo_buffer)
        buf_col     = _GREEN if buffer_size == FIFO_MAX_LEN else _YELLOW

        # ── Label de la vela ──────────────────────────────────────────────────
        if is_first:
            label = f"{_B}{_CYAN}[ INICIO ]{_R}"
        elif is_last:
            label = f"{_B}{_CYAN}[  FIN   ]{_R}"
        else:
            label = f"{_DIM}[#{i+1:>5}]{_R}"

        # ── Línea separadora ──────────────────────────────────────────────────
        print(f"  {_DIM}{'─'*68}{_R}")

        # ── Línea de precio e indicadores ────────────────────────────────────
        print(
            f"  {label}  {_B}{candle.formatted_date}{_R}  "
            f"│  C: {_B}${candle.close:>8.2f}{_R}  "
            f"│  EMA200: {_B}{ema200_str:>8}{_R}  "
            f"│  {pos_str}  "
            f"│  {buf_col}buf {buffer_size}/{FIFO_MAX_LEN}{_R}"
        )

        # ── Línea de indicadores ──────────────────────────────────────────────
        print(
            f"  {'':>11}  "
            f"RSI(2): {rsi2_col}{rsi2_str:>5}{_R}  "
            f"│  RSI(14): {rsi14_str:>5}  "
            f"│  ATR: {atr_str:>7}  "
            f"│  ADX: {adx_col}{_B}{adx_str:>5}{_R}"
        )

        # ── Línea de análisis (régimen) ───────────────────────────────────────
        print(
            f"  {'':>11}  "
            f"🌤  Régimen: {regime_col}{_B}{regime_name:<25}{_R}  "
            f"│  Sesgo: {bias_str}"
        )

        return


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = os.path.join(os.path.dirname(__file__), "Data_Leo")

ASSETS = {
    "1": ("NASDAQ_COST", "COST_1D_3000Bars.json"),
    "2": ("NYSE_LMT",    "LMT_1D_3000Bars.json"),
    "3": ("NASDAQ_HON",  "HON_1D_3000Bars.json"),
    "4": ("NYSE_GWW",    "GWW_1D_3000Bars.json"),
    "5": ("NYSE_NOC",    "NOC_1D_3000Bars.json"),
    "0": None,  # Ruta manual
}


def _select_asset() -> str:
    """Menú interactivo para seleccionar el activo a testear."""
    print("\n┌─────────────────────────────────────────┐")
    print("│  TRADING ENGINE — Selector de Activo    │")
    print("├─────────────────────────────────────────┤")
    for key, val in ASSETS.items():
        if val is None:
            print(f"│  {key}: Ruta manual                       │")
        else:
            folder, _ = val
            print(f"│  {key}: {folder:<34} │")
    print("└─────────────────────────────────────────┘")

    choice = input("Selección [1]: ").strip() or "1"

    if choice not in ASSETS:
        logger.warning(f"Opción '{choice}' inválida. Usando COST por defecto.")
        choice = "1"

    if ASSETS[choice] is None:
        path = input("Ingresá la ruta al archivo JSON: ").strip()
        return path

    folder, fname = ASSETS[choice]

    # Buscar el archivo en Data_Leo
    candidate = os.path.join(DATA_DIR, folder, fname)
    if os.path.exists(candidate):
        return candidate

    # Si no existe con ese nombre exacto, buscar el primer JSON en esa carpeta
    folder_path = os.path.join(DATA_DIR, folder)
    if os.path.isdir(folder_path):
        jsons = [f for f in os.listdir(folder_path) if f.endswith(".json")]
        if jsons:
            return os.path.join(folder_path, jsons[0])

    raise FileNotFoundError(
        f"No se encontró ningún JSON en '{folder_path}'.\n"
        f"Verificá que la carpeta Data_Leo esté correctamente ubicada en:\n"
        f"  {DATA_DIR}"
    )


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  SISTEMA DE TRADING ALGORÍTMICO — Motor + Pronóstico del Clima")
    print("=" * 70)

    try:
        file_path = _select_asset()
    except (FileNotFoundError, KeyboardInterrupt) as e:
        logger.error(f"Error seleccionando activo: {e}")
        raise SystemExit(1)

    # ── Carga de datos ────────────────────────────────────────────────────────
    loader = JSONDataLoader()
    candles = loader.load_from_json(file_path)
    print(f"\n  ✓ {len(candles)} velas cargadas desde:\n    {os.path.abspath(file_path)}\n")

    # ── Ejecución del backtest ────────────────────────────────────────────────
    from Strategys_Backtesting.connors_rsi2 import RSI2Strategy
    engine = TradingEngine(strategy=RSI2Strategy(), initial_balance=100_000.0)
    engine.run_backtest(candles)
