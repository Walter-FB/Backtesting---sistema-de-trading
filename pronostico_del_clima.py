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
from indicators import adx as _adx, atr as _atr, rsi as _rsi


# ── Constantes de períodos ────────────────────────────────────────────────────
RSI2_PERIOD: int = 2    # RSI de corto plazo — señal de reversión a la media
ATR_PERIOD:  int = 14   # Volatilidad — para sizing y gestión de riesgo
ADX_PERIOD:  int = 14   # Fuerza de tendencia — para clasificar el régimen


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1: CÁLCULO DE INDICADORES
# ═══════════════════════════════════════════════════════════════════════════════
#
# Este módulo ya NO implementa sus propios indicadores: los toma de
# indicators.py, que es la única implementación de cada uno en todo el sistema.
#
# Antes había tres implementaciones paralelas del RSI, el ATR y el ADX (acá,
# en indicators.py y en crypto_data_loader.py) y daban números distintos sobre
# los mismos datos. Una estrategia que usara `indicators.rsi()` y otra que
# leyera `candle.rsi` estaban mirando indicadores diferentes creyendo que eran
# el mismo. Colapsarlas en una sola hace imposible que vuelvan a divergir.

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

    # La vela actual es la última del buffer
    current = fifo[-1]

    # ── Calcular y asignar (una sola implementación: indicators.py) ───────────
    current.rsi_2  = _rsi(fifo, RSI2_PERIOD)
    current.atr_14 = _atr(fifo, ATR_PERIOD)
    current.adx_14 = _adx(fifo, ADX_PERIOD)

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
