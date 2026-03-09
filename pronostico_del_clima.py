"""
pronostico_del_clima.py — Capa de Análisis e Indicadores del Mercado
=====================================================================
Centraliza TODO el análisis de mercado del sistema.

Responsabilidades:
  1. Calcular los indicadores que NO vienen en el JSON:
       - RSI(2)  : sensibilidad de corto plazo para reversión a la media
       - ATR(14) : volatilidad, usado para sizing y stops
       - ADX(14) : fuerza de la tendencia (clave para el régimen)

  2. Los indicadores que SÍ vienen en el JSON (RSI14, MACD, EMAs, BB)
     ya están cargados en cada Candle por data_loader.py — no se recalculan.

  3. Detectar el régimen de mercado actual (RegimeDetector).

  4. [Futuro] Análisis de volumen, señales de entrada/salida, scoring, etc.

REGLA DE ORO: Todo cálculo usa SÓLO datos del fifo_buffer actual.
              Jamás se accede a datos futuros (sin look-ahead bias).

Arquitectura del sistema:
  data_loader.py          → carga JSON → List[Candle]
  engine.py               → loop FIFO y orquestación
  pronostico_del_clima.py → análisis, cálculos, régimen  ← ESTE ARCHIVO
  analysis.py             → Enum MarketRegime (solo definición)
  models.py               → clase Candle (estructura de datos)
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime


# ── Constantes de períodos ────────────────────────────────────────────────────
RSI2_PERIOD: int = 2    # RSI de corto plazo — señal de reversión a la media
ATR_PERIOD:  int = 14   # Volatilidad — para sizing y gestión de riesgo
ADX_PERIOD:  int = 14   # Fuerza de tendencia — para clasificar el régimen


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1: FUNCIONES DE CÁLCULO
# (solo los indicadores ausentes en el JSON)
# ═══════════════════════════════════════════════════════════════════════════════

def _calc_rsi(closes: list, period: int) -> Optional[float]:
    """
    RSI (Relative Strength Index) usando el método de suavizado de Wilder.
    Requiere al menos period + 1 cierres en el buffer.

    Ejemplo: RSI(2) necesita 3 cierres mínimo.
    """
    if len(closes) < period + 1:
        return None

    relevant = closes[-(period + 1):]
    gains, losses = [], []

    for i in range(1, len(relevant)):
        delta = relevant[i] - relevant[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _calc_atr(highs: list, lows: list, closes: list, period: int) -> Optional[float]:
    """
    ATR (Average True Range) — medida de volatilidad real de la vela.
    True Range = max(H-L, |H-C_prev|, |L-C_prev|)

    Requiere al menos period + 1 velas en el buffer.
    """
    n = len(closes)
    if n < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return None

    true_ranges = []
    start = max(1, n - period)

    for i in range(start, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    return sum(true_ranges[-period:]) / period


def _calc_adx(highs: list, lows: list, closes: list, period: int) -> Optional[float]:
    """
    ADX (Average Directional Index) — mide la FUERZA de la tendencia (no dirección).

    `period` = 14 (ADX_PERIOD): ventana de suavizado de Wilder.
    NO son las 250 del FIFO — el FIFO garantiza historia disponible;
    el period define cuántas velas usa el cálculo (ventana = 2×14 = 28 velas).

    El ADX no está en los JSONs del proveedor → siempre se calcula aquí.

    Proceso:
      1. Calcular TR, +DM y -DM para cada vela de la ventana
      2. Suavizar con el método de Wilder
      3. Calcular +DI y -DI (dirección normalizada contra la volatilidad)
      4. DX = qué tan separadas están +DI y -DI → fuerza del movimiento
    """
    total_candles        = len(closes)
    min_candles_required = period * 2 + 1

    if total_candles < min_candles_required or len(highs) < min_candles_required or len(lows) < min_candles_required:
        return None

    # Ventana de análisis: 2×period velas (14 para arrancar Wilder + 14 para estabilizarlo)
    calculation_window = min(total_candles, period * 2)
    true_ranges, bullish_dm_list, bearish_dm_list = [], [], []

    for i in range(total_candles - calculation_window, total_candles):
        high       = highs[i]
        low        = lows[i]
        prev_high  = highs[i - 1]
        prev_low   = lows[i - 1]
        prev_close = closes[i - 1]

        # True Range: rango real considerando gaps con la vela anterior
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))

        # +DM: movimiento alcista — solo cuenta si fue mayor que el bajista
        bullish_dm = max(high - prev_high, 0) if (high - prev_high) > (prev_low - low) else 0
        # -DM: movimiento bajista — solo cuenta si fue mayor que el alcista
        bearish_dm = max(prev_low - low,   0) if (prev_low - low) > (high - prev_high) else 0

        true_ranges.append(true_range)
        bullish_dm_list.append(bullish_dm)
        bearish_dm_list.append(bearish_dm)

    if len(true_ranges) < period:
        return None

    def wilder_smooth(data_series: list, smoothing_period: int) -> float:
        """Primera media simple, luego suavizado exponencial de Wilder."""
        running_total = sum(data_series[:smoothing_period])
        for new_value in data_series[smoothing_period:]:
            running_total = running_total - (running_total / smoothing_period) + new_value
        return running_total

    smoothed_atr        = wilder_smooth(true_ranges,     period)
    smoothed_bullish_dm = wilder_smooth(bullish_dm_list, period)
    smoothed_bearish_dm = wilder_smooth(bearish_dm_list, period)

    if smoothed_atr == 0:
        return 0.0

    # +DI y -DI: movimiento direccional normalizado contra la volatilidad real (ATR)
    bullish_directional_index  = 100 * smoothed_bullish_dm / smoothed_atr
    bearish_directional_index  = 100 * smoothed_bearish_dm / smoothed_atr
    total_directional_strength = bullish_directional_index + bearish_directional_index

    if total_directional_strength == 0:
        return 0.0

    # DX: qué tan separadas están las dos líneas → convicción del movimiento
    directional_index = 100 * abs(bullish_directional_index - bearish_directional_index) / total_directional_strength
    return directional_index


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2: ACTUALIZACIÓN DE INDICADORES EN LA VELA ACTUAL
# ═══════════════════════════════════════════════════════════════════════════════

def compute_and_set_indicators(fifo: deque) -> None:
    """
    Calcula los indicadores que NO vienen en el JSON y los escribe
    directamente en la última vela del buffer (la vela actual).

    Indicadores calculados aquí:
      - rsi_2  : RSI(2)  — señal de reversión a la media
      - atr_14 : ATR(14) — volatilidad para sizing y stops
      - adx_14 : ADX(14) — fuerza de tendencia para el régimen

    Indicadores que YA vienen del JSON (no se tocan):
      - rsi         : RSI(14) del proveedor
      - macd_line, signal_line, macd_histogram
      - ema_20, ema_50, ema_100, ema_200
      - bb_mid, bb_upper, bb_lower

    REGLA DE ORO: Solo usa datos presentes en el fifo_buffer.
                  Nunca accede a velas futuras.

    Parámetros
    ----------
    fifo : deque[Candle] — buffer FIFO con maxlen=250
    """
    if not fifo:
        return

    # Extraer series en orden cronológico desde el buffer
    closes = [c.close for c in fifo]
    highs  = [c.high  for c in fifo]
    lows   = [c.low   for c in fifo]

    # La vela actual es la última del buffer
    current = fifo[-1]

    # ── Calcular y asignar ────────────────────────────────────────────────────
    current.rsi_2  = _calc_rsi(closes, RSI2_PERIOD)
    current.atr_14 = _calc_atr(highs, lows, closes, ATR_PERIOD)
    current.adx_14 = _calc_adx(highs, lows, closes, ADX_PERIOD)

    # EMA(200) del proveedor ya está en current.ema_200 — se usa directamente
    # en RegimeDetector para el sesgo estructural. No se recalcula.


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3: DETECTOR DE RÉGIMEN DE MERCADO
# ═══════════════════════════════════════════════════════════════════════════════

class RegimeDetector:
    """
    Clasifica el mercado en uno de los 5 estados de MarketRegime,
    basándose en el ADX calculado y la EMA(200) del proveedor.

    Lógica del "Semáforo":
      ┌────────────────────────────────────────────────────────┐
      │  ADX < 20              → RANGING_MEAN_REVERSION        │
      │  20 ≤ ADX ≤ 25         → HIGH_VOLATILITY_CASH          │
      │  ADX > 25, subiendo    → TRENDING (BULLISH o BEARISH)  │
      │  ADX > 40              → HIGH_VOLATILITY_CASH          │
      │  Sin datos suficientes → WAITING_FOR_DATA              │
      └────────────────────────────────────────────────────────┘

    Sesgo estructural (bullish_bias):
      True  → precio > EMA(200) — contexto alcista estructural
      False → precio ≤ EMA(200) — contexto bajista estructural
      None  → EMA(200) no disponible en el JSON para esa vela todavía
    """

    adx_threshold:  int = 25   # umbral principal tendencia/rango
    _ADX_EXHAUSTION: int = 40   # zona de agotamiento/reversión brusca
    _ADX_LOWER_BAND: int = 20   # límite inferior del rango

    def __init__(self) -> None:
        self._prev_adx: Optional[float] = None
        self._last_regime: MarketRegime = MarketRegime.WAITING_FOR_DATA
        self._last_bullish_bias: Optional[bool] = None

    # ── Propiedad pública ─────────────────────────────────────────────────────

    @property
    def bullish_bias(self) -> Optional[bool]:
        """
        Sesgo alcista estructural basado en EMA(200) del proveedor.

        Retorna True/False/None según la posición del precio vs EMA200.
        """
        return self._last_bullish_bias

    # ── Método principal ──────────────────────────────────────────────────────

    def detect(self, fifo: deque) -> MarketRegime:
        """
        Analiza el fifo_buffer y retorna el régimen actual del mercado.

        Parámetros
        ----------
        fifo : deque[Candle] — buffer FIFO en su estado actual.

        Retorna
        -------
        MarketRegime — clasificación actual del mercado.
        """
        # Guardia: buffer vacío
        if not fifo:
            self._last_regime = MarketRegime.WAITING_FOR_DATA
            self._last_bullish_bias = None
            return self._last_regime

        current   = fifo[-1]
        adx: Optional[float]   = current.adx_14    # calculado por compute_and_set_indicators
        ema200: Optional[float] = current.ema_200   # leído directamente del JSON

        # Actualizar sesgo estructural (usa EMA200 del proveedor)
        if ema200 is not None:
            self._last_bullish_bias = current.close > ema200
        else:
            self._last_bullish_bias = None

        # Guardia: período de calentamiento (ADX o EMA200 aún no disponibles)
        if adx is None or ema200 is None:
            self._prev_adx = adx
            self._last_regime = MarketRegime.WAITING_FOR_DATA
            return self._last_regime

        # ── Semáforo ADX ─────────────────────────────────────────────────────

        if adx > self._ADX_EXHAUSTION:
            # Tendencia agotada — reversión brusca probable
            regime = MarketRegime.HIGH_VOLATILITY_CASH

        elif adx < self._ADX_LOWER_BAND:
            # Mercado lateral / reversión a la media
            regime = MarketRegime.RANGING_MEAN_REVERSION

        elif adx <= self.adx_threshold:
            # Zona gris 20–25 — transición, no operar
            regime = MarketRegime.HIGH_VOLATILITY_CASH

        else:
            # ADX > 25 — posible tendencia, verificar pendiente
            adx_slope_up = (self._prev_adx is None or adx >= self._prev_adx)

            if adx_slope_up:
                # Tendencia confirmada — dirección según sesgo estructural
                regime = (MarketRegime.TRENDING_BULLISH
                          if self._last_bullish_bias
                          else MarketRegime.TRENDING_BEARISH)
            else:
                # ADX > 25 pero cayendo — posible agotamiento
                regime = MarketRegime.HIGH_VOLATILITY_CASH

        # Actualizar estado interno
        self._prev_adx = adx
        self._last_regime = regime
        return regime

    # ── Repr ─────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        bias_str = (
            "BULLISH" if self._last_bullish_bias is True
            else "BEARISH" if self._last_bullish_bias is False
            else "N/A"
        )
        adx_str = f"{self._prev_adx:.2f}" if self._prev_adx is not None else "N/A"
        return (
            f"RegimeDetector("
            f"regime={self._last_regime.name} | "
            f"bias={bias_str} | "
            f"ADX={adx_str})"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# [FUTURO] BLOQUE 4: ANÁLISIS DE VOLUMEN
# ═══════════════════════════════════════════════════════════════════════════════
# Acá irá la lógica de tratamiento de volumen:
#   - volume_vs_30d_avg_pct del JSON
#   - Detección de volumen anómalo
#   - Confirmación de señales con volumen
#
# def analyze_volume(fifo: deque) -> dict:
#     pass


# ═══════════════════════════════════════════════════════════════════════════════
# [FUTURO] BLOQUE 5: SCORING / SEÑALES
# ═══════════════════════════════════════════════════════════════════════════════
# Acá irá la lógica de señales de entrada/salida:
#   - Confirmación de RSI(2) en zona de sobreventa/sobrecompra
#   - Score compuesto (ADX + RSI + volumen)
#
# def compute_signal_score(fifo: deque, regime: MarketRegime) -> float:
#     pass
