"""
clasico_adx_ema200.py — Pronóstico de Clima Clásico (ADX + EMA200)
=====================================================================
Envuelve el RegimeDetector original (pronostico_del_clima.py) bajo la
interfaz ClimateProvider, para que el engine lo trate como un pronóstico
de clima intercambiable más — el mismo motor que antes, ahora enchufable.

Este es el clima por DEFECTO del sistema (registrado como "clasico_adx_ema200"
en climate_factory.py). No cambia ni un número de la lógica original: solo
la expone bajo el contrato genérico ClimateProvider.
"""

from __future__ import annotations

from collections import deque

from climate_provider import ClimateProvider, ClimateReading
from pronostico_del_clima import RegimeDetector


class ClassicRegimeClimate(ClimateProvider):
    """
    Pronóstico de clima clásico: ADX(14) para fuerza de tendencia +
    EMA(200) para sesgo estructural. Clasifica en los 5 estados de
    MarketRegime (ver analysis.py).
    """

    def __init__(self) -> None:
        self._detector = RegimeDetector()

    def detect(self, fifo: deque) -> ClimateReading:
        regime = self._detector.detect(fifo)
        return ClimateReading(
            label=regime.name,
            bullish_bias=self._detector.bullish_bias,
            regime=regime,
        )
