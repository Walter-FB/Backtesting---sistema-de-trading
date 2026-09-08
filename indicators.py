"""
indicators.py — Toolkit de Indicadores Técnicos
================================================
Funciones puras para calcular indicadores técnicos a partir del buffer FIFO
(o de cualquier secuencia de Candle ordenada cronológicamente).

REGLA DE ORO — Sin look-ahead
------------------------------
Todas las funciones de este módulo leen ÚNICAMENTE los datos ya presentes
en la secuencia que reciben (fifo[-1] es "hoy", fifo[-2] es "ayer", etc.).
Ninguna función accede a datos futuros. Esto las hace seguras de usar tanto
en el loop del engine (backtest) como en el loop de paper trading (en vivo).

Filosofía de diseño
--------------------
Antes, cada estrategia (o pronostico_del_clima.py) reimplementaba sus propios
cálculos de RSI/ATR/ADX. Esto centraliza esa lógica en un solo lugar:
armar una estrategia nueva es importar la función que necesitás y combinar
condiciones, no reescribir el indicador de cero.

Uso
---
    from indicators import ema, rsi, atr, adx, macd, bollinger_bands

    fifo: deque[Candle] = ...
    valor_rsi14 = rsi(fifo, period=14)
    valor_ema50 = ema(fifo, period=50)
"""

from __future__ import annotations

from collections import deque
from typing import List, Optional, Sequence, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ═══════════════════════════════════════════════════════════════════════════════

def _closes(fifo: Sequence, field: str = "close") -> List[float]:
    """Extrae la serie de un campo (por defecto 'close') del buffer, en orden cronológico."""
    return [getattr(c, field) for c in fifo]


# ═══════════════════════════════════════════════════════════════════════════════
# MEDIAS MÓVILES
# ═══════════════════════════════════════════════════════════════════════════════

def sma(fifo: Sequence, period: int, field: str = "close") -> Optional[float]:
    """
    Media Móvil Simple sobre las últimas `period` velas del buffer.

    Retorna None si el buffer no tiene suficientes velas todavía.
    """
    values = _closes(fifo, field)
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(fifo: Sequence, period: int, field: str = "close") -> Optional[float]:
    """
    Media Móvil Exponencial sobre TODA la serie disponible en el buffer,
    usando `period` como constante de suavizado (no requiere `period` velas
    exactas, pero el valor es más confiable cuanto más historial haya).

    Fórmula: EMA_hoy = precio_hoy × k + EMA_ayer × (1 − k),  k = 2 / (period + 1)
    Semilla: SMA de las primeras `period` velas.

    Retorna None si el buffer tiene menos de `period` velas.
    """
    values = _closes(fifo, field)
    if len(values) < period:
        return None

    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    ema_val = seed
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


# ═══════════════════════════════════════════════════════════════════════════════
# RSI
# ═══════════════════════════════════════════════════════════════════════════════

def rsi(fifo: Sequence, period: int = 14, field: str = "close") -> Optional[float]:
    """
    Relative Strength Index de Wilder sobre las últimas `period + 1` velas
    del buffer (necesita `period` variaciones, por lo tanto `period + 1` precios).

    Retorna None si no hay suficientes velas.
    """
    values = _closes(fifo, field)
    if len(values) < period + 1:
        return None

    window = values[-(period + 1):]
    gains, losses = 0.0, 0.0
    for prev, curr in zip(window, window[1:]):
        delta = curr - prev
        if delta >= 0:
            gains += delta
        else:
            losses += -delta

    avg_gain = gains / period
    avg_loss = losses / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ═══════════════════════════════════════════════════════════════════════════════
# ATR (Average True Range)
# ═══════════════════════════════════════════════════════════════════════════════

def atr(fifo: Sequence, period: int = 14) -> Optional[float]:
    """
    Average True Range sobre las últimas `period + 1` velas del buffer
    (necesita el close previo para calcular el True Range de cada vela).

    True Range = max(high−low, |high−close_prev|, |low−close_prev|)

    Retorna None si no hay suficientes velas.
    """
    if len(fifo) < period + 1:
        return None

    window = list(fifo)[-(period + 1):]
    true_ranges = []
    for prev, curr in zip(window, window[1:]):
        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )
        true_ranges.append(tr)

    return sum(true_ranges) / period


# ═══════════════════════════════════════════════════════════════════════════════
# ADX (Average Directional Index)
# ═══════════════════════════════════════════════════════════════════════════════

def adx(fifo: Sequence, period: int = 14) -> Optional[float]:
    """
    Average Directional Index de Wilder — mide la FUERZA de una tendencia
    (no la dirección). Requiere aproximadamente 2×period velas para ser
    confiable (un período para +DI/−DI, otro para suavizar el DX en ADX).

    Retorna None si no hay suficientes velas.
    """
    needed = period * 2 + 1
    if len(fifo) < needed:
        return None

    window = list(fifo)[-needed:]

    plus_dm, minus_dm, trs = [], [], []
    for prev, curr in zip(window, window[1:]):
        up_move = curr.high - prev.high
        down_move = prev.low - curr.low

        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)

        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )
        trs.append(tr)

    def _wilder_smooth(series: List[float], period: int) -> List[float]:
        smoothed = [sum(series[:period])]
        for val in series[period:]:
            smoothed.append(smoothed[-1] - (smoothed[-1] / period) + val)
        return smoothed

    smoothed_tr = _wilder_smooth(trs, period)
    smoothed_plus_dm = _wilder_smooth(plus_dm, period)
    smoothed_minus_dm = _wilder_smooth(minus_dm, period)

    dx_values = []
    for tr_val, pdm, mdm in zip(smoothed_tr, smoothed_plus_dm, smoothed_minus_dm):
        if tr_val == 0:
            dx_values.append(0.0)
            continue
        plus_di = 100.0 * (pdm / tr_val)
        minus_di = 100.0 * (mdm / tr_val)
        di_sum = plus_di + minus_di
        dx = 100.0 * (abs(plus_di - minus_di) / di_sum) if di_sum != 0 else 0.0
        dx_values.append(dx)

    if len(dx_values) < period:
        return None

    return sum(dx_values[-period:]) / period


# ═══════════════════════════════════════════════════════════════════════════════
# MACD
# ═══════════════════════════════════════════════════════════════════════════════

def macd(
    fifo: Sequence,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    field: str = "close",
) -> Optional[Tuple[float, float, float]]:
    """
    MACD (Moving Average Convergence Divergence).

    Retorna (macd_line, signal_line, histogram), o None si no hay
    suficiente historial para calcular la EMA lenta + la señal.
    """
    values = _closes(fifo, field)
    if len(values) < slow + signal:
        return None

    def _ema_series(series: List[float], period: int) -> List[float]:
        k = 2.0 / (period + 1)
        seed = sum(series[:period]) / period
        out = [seed]
        for price in series[period:]:
            out.append(price * k + out[-1] * (1 - k))
        return out

    ema_fast_series = _ema_series(values, fast)
    ema_slow_series = _ema_series(values, slow)

    # Alinear ambas series al mismo largo (la EMA rápida arranca antes)
    offset = len(ema_fast_series) - len(ema_slow_series)
    macd_series = [
        f - s for f, s in zip(ema_fast_series[offset:], ema_slow_series)
    ]

    if len(macd_series) < signal:
        return None

    signal_series = _ema_series(macd_series, signal)
    macd_line = macd_series[-1]
    signal_line = signal_series[-1]
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


# ═══════════════════════════════════════════════════════════════════════════════
# BANDAS DE BOLLINGER
# ═══════════════════════════════════════════════════════════════════════════════

def bollinger_bands(
    fifo: Sequence,
    period: int = 20,
    num_std: float = 2.0,
    field: str = "close",
) -> Optional[Tuple[float, float, float]]:
    """
    Bandas de Bollinger: (banda_media, banda_superior, banda_inferior).

    banda_media = SMA(period)
    bandas       = banda_media ± num_std × desvío estándar de la muestra

    Retorna None si no hay suficientes velas.
    """
    values = _closes(fifo, field)
    if len(values) < period:
        return None

    window = values[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std_dev = variance ** 0.5

    upper = mid + num_std * std_dev
    lower = mid - num_std * std_dev
    return mid, upper, lower


# ═══════════════════════════════════════════════════════════════════════════════
# CRUCES (helper genérico para estrategias de cruce de medias, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

def crossed_above(prev_a: Optional[float], curr_a: Optional[float],
                   prev_b: Optional[float], curr_b: Optional[float]) -> bool:
    """True si la serie A cruzó por ENCIMA de la serie B entre ayer y hoy."""
    if None in (prev_a, curr_a, prev_b, curr_b):
        return False
    return prev_a <= prev_b and curr_a > curr_b


def crossed_below(prev_a: Optional[float], curr_a: Optional[float],
                   prev_b: Optional[float], curr_b: Optional[float]) -> bool:
    """True si la serie A cruzó por DEBAJO de la serie B entre ayer y hoy."""
    if None in (prev_a, curr_a, prev_b, curr_b):
        return False
    return prev_a >= prev_b and curr_a < curr_b
