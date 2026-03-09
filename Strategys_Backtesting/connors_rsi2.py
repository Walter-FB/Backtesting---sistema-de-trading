"""
connors_rsi2.py — Estrategia RSI(2) de Larry Connors
=====================================================
Primera estrategia del sistema. Diseñada para capturar reversiones
a la media en mercados lateralizados con sesgo alcista estructural.

Filosofía (Larry Connors — "Short Term Trading Strategies That Work"):
  El RSI(2) es un oscilador de ultra corto plazo. Cuando cae por debajo
  de 10 en un activo estructuralmente alcista (precio > EMA200), el activo
  está estadísticamente sobrevendido y tiene alta probabilidad de recuperarse
  hacia la media en los próximos días.

Reglas de la estrategia:
  ENTRADA (señal al cierre, ejecución al OPEN del día siguiente):
    1. bullish_bias = True   → precio de cierre > EMA(200) — filtro estructural
    2. regime = RANGING_MEAN_REVERSION (ADX < 20) — mercado sin tendencia fuerte
    3. rsi_2 < 10            → sobreventa extrema de corto plazo

  SALIDA (señal al cierre, ejecución al OPEN del día siguiente):
    • Target   : rsi_2 > 50  → reversión a la media completada
    • Time-stop: 10 velas    → evita quedar atrapado si el mercado sigue bajando

REGLA DE ORO: Este módulo jamás accede a datos futuros.
              Solo lee el fifo_buffer en su estado actual (vela actual al final).

Futuras estrategias seguirán la misma interfaz:
  - check_entry(fifo, regime, bullish_bias) -> bool
  - check_exit(fifo, candles_held) -> Optional[str]
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from signal_provider import SignalProvider


# ── Parámetros de la estrategia ───────────────────────────────────────────────
RSI2_ENTRY_THRESHOLD: float = 10.0   # RSI(2) debe estar DEBAJO de este valor
RSI2_EXIT_THRESHOLD:  float = 50.0   # RSI(2) debe cruzar ENCIMA de este valor
TIME_STOP_CANDLES:    int   = 10     # Máximo de velas permitidas en posición

# ── Parámetros de gestión de riesgo ──────────────────────────────────────────
RISK_PCT:        float = 0.01   # Porcentaje del capital a arriesgar por trade (1%)
ATR_MULTIPLIER:  float = 2.0    # Multiplicador de volatilidad para el riesgo


# ═══════════════════════════════════════════════════════════════════════════════
# ESTRATEGIA RSI(2) — CONNORS
# ═══════════════════════════════════════════════════════════════════════════════

class RSI2Strategy(SignalProvider):
    """
    Implementación de la estrategia de reversión a la media de Larry Connors.
    Hereda de SignalProvider e implementa el contrato check_entry / check_exit.

    Interfaz pública:
      check_entry(fifo, regime, bullish_bias) -> bool
      check_exit(fifo, candles_held)          -> Optional[str]

    No guarda estado entre llamadas — cada evaluación es independiente.
    Esto la hace predecible y testeable.
    """

    def check_entry(
        self,
        fifo: deque,
        regime: MarketRegime,
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Evalúa si se cumplen TODAS las condiciones de entrada.
        La señal se detecta al cierre de la vela; la ejecución ocurre al
        precio de apertura de la vela siguiente (responsabilidad del engine).

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO con la vela actual al final
        regime       : MarketRegime  — régimen detectado por pronostico_del_clima
        bullish_bias : Optional[bool]
                       True  → precio > EMA200 (alcista)
                       False → precio ≤ EMA200 (bajista)
                       None  → EMA200 no disponible aún

        Retorna
        -------
        bool
            True  → señal de entrada confirmada (entrar al open siguiente)
            False → no se cumplen las condiciones

        Condiciones (todas deben cumplirse):
          1. bullish_bias is True  → precio > EMA(200)
          2. regime == RANGING_MEAN_REVERSION
          3. rsi_2 < 10            → sobreventa extrema
          4. close <= bb_lower     → precio en/bajo la BB Inferior (doble confirmación)
        """
        if not fifo:
            return False

        current = fifo[-1]

        # ── Condición 1: Sesgo alcista estructural (precio > EMA200) ─────────
        if bullish_bias is not True:
            return False

        # ── Condición 2: Mercado en rango lateral (ADX < 20) ─────────────────
        #if regime != MarketRegime.RANGING_MEAN_REVERSION:
         #   return False

        # ── Condición 3: RSI(2) en zona de sobreventa extrema (<10) ──────────
        if current.rsi_2 is None or current.rsi_2 >= RSI2_ENTRY_THRESHOLD:
            return False

        # ── Condición 4: Precio tocó/cruzó la Banda de Bollinger Inferior ────
        # Doble confirmación de agotamiento: el mercado no solo tiene RSI
        # sobrevendido, sino que el precio ha alcanzado el extremo estadístico
        # de la distribución de volatilidad actual.
        if current.bb_lower is None or current.close > current.bb_lower:
            return False

        # Todas las condiciones se cumplen
        return True

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Evalúa si se debe cerrar la posición actualmente abierta.
        Verifica el target de RSI(2) y el time-stop.
        La señal se detecta al cierre; la ejecución ocurre al open siguiente.

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO con la vela actual al final
        candles_held : int — cantidad de velas que lleva abierta la posición
                            (se incrementa en el engine por cada vela procesada)

        Retorna
        -------
        str  → razón de salida:
               "RSI_TARGET"  : RSI(2) cruzó por encima de 50 (target alcanzado)
               "TIME_STOP"   : se completaron las 10 velas máximo
        None → mantener la posición abierta
        """
        # ── Guardia: buffer vacío ─────────────────────────────────────────────
        if not fifo:
            return "TIME_STOP"

        current = fifo[-1]

        # ── Time-stop: máximo de velas superado ──────────────────────────────
        if candles_held >= TIME_STOP_CANDLES:
            return "TIME_STOP"

        # ── Target: RSI(2) cruza por encima de 50 ────────────────────────────
        if current.rsi_2 is not None and current.rsi_2 > RSI2_EXIT_THRESHOLD:
            return "RSI_TARGET"

        # Mantener posición
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# RISK MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    """
    Calcula el tamaño de posición para igualar el riesgo entre trades.

    Cada trade arriesga exactamente `risk_pct` del capital disponible.
    La volatilidad medida por ATR determina cuántas acciones comprar:
    más volátil el activo → menos acciones → mismo riesgo en dólares.

    Fórmula:
        Quantity = (Balance × risk_pct) / (ATR × atr_multiplier)

    Ejemplo con COST:
        Balance = $100,000 | ATR = $13.45 | risk_pct = 1% | multiplier = 2.0
        Quantity = (100,000 × 0.01) / (13.45 × 2.0) = 1,000 / 26.9 ≈ 37 acciones
        Riesgo real = 37 × 13.45 × 2.0 = $995.3 ≈ 1% del capital ✓

    Atributos
    ---------
    risk_pct       : float — fracción del capital a arriesgar (default: 0.01)
    atr_multiplier : float — multiplicador de distancia de riesgo (default: 2.0)
    """

    def __init__(
        self,
        risk_pct: float = RISK_PCT,
        atr_multiplier: float = ATR_MULTIPLIER,
    ) -> None:
        self.risk_pct       = risk_pct
        self.atr_multiplier = atr_multiplier

    def compute_quantity(
        self,
        balance: float,
        atr: Optional[float],
    ) -> float:
        """
        Calcula la cantidad de acciones a comprar para el próximo trade.

        Parámetros
        ----------
        balance : float          — capital disponible ANTES del trade
        atr     : Optional[float] — ATR(14) de la vela de señal

        Retorna
        -------
        float
            Cantidad de acciones (no redondeada — permite fracciones para cripto).
            0.0 si ATR no disponible o parámetros inválidos.
        """
        if atr is None or atr <= 0 or balance <= 0:
            return 0.0

        qty = (balance * self.risk_pct) / (atr * self.atr_multiplier)
        return max(0.0, qty)

    def compute_risk_amount(self, balance: float) -> float:
        """
        Retorna el monto en dólares que se arriesga en el próximo trade.

        Parámetros
        ----------
        balance : float — capital actual

        Retorna
        -------
        float — balance × risk_pct (ej: $100,000 × 0.01 = $1,000)
        """
        return balance * self.risk_pct
