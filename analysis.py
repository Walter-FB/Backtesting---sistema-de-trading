"""
analysis.py — Enum de Regímenes de Mercado
===========================================
Define los 5 estados posibles del mercado.

La lógica de detección (RegimeDetector) vive en pronostico_del_clima.py.
Este archivo es solo la definición del vocabulario compartido del sistema.
"""

from enum import Enum, auto


class MarketRegime(Enum):
    """
    Estados posibles del mercado.

    TRENDING_BULLISH      : Tendencia alcista confirmada (ADX > 25, precio > EMA200).
    TRENDING_BEARISH      : Tendencia bajista confirmada (ADX > 25, precio < EMA200).
    RANGING_MEAN_REVERSION: Mercado lateral (ADX < 20) — zona operable para reversión.
    HIGH_VOLATILITY_CASH  : Zona de riesgo — no operar
                            (ADX 20–25, ADX > 40, o ADX > 25 con pendiente bajista).
    WAITING_FOR_DATA      : Buffer insuficiente para calcular indicadores.
                            Estado neutro durante el calentamiento inicial.
    """
    TRENDING_BULLISH       = auto()
    TRENDING_BEARISH       = auto()
    RANGING_MEAN_REVERSION = auto()
    HIGH_VOLATILITY_CASH   = auto()
    WAITING_FOR_DATA       = auto()
