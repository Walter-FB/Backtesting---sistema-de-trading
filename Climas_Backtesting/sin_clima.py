"""
sin_clima.py — Pronóstico de Clima Nulo
==========================================
Para estrategias que no dependen de ningún filtro de régimen de mercado.
Siempre retorna un clima neutro ("SIN_CLIMA", sin sesgo), para que el
engine tenga siempre un ClimateProvider inyectado (nunca None) incluso
cuando la estrategia no lo necesita.
"""

from __future__ import annotations

from collections import deque

from climate_provider import ClimateProvider, ClimateReading


class NullClimateProvider(ClimateProvider):
    """Pronóstico neutro — no clasifica nada, siempre retorna SIN_CLIMA."""

    def detect(self, fifo: deque) -> ClimateReading:
        return ClimateReading(label="SIN_CLIMA", bullish_bias=None)
