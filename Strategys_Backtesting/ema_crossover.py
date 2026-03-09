"""
ema_crossover.py — Estrategia de Cruce de Medias Móviles
========================================================
Una estrategia de seguimiento de tendencia de mediano plazo basada
en el cruce de la EMA rápida (20) y la EMA lenta (50).

Reglas de la estrategia:
  ENTRADA:
    1. bullish_bias == True   → El precio está por encima de la EMA(200)
    2. Golden Cross           → EMA(20) cruza por encima de la EMA(50)

  SALIDA:
    1. Death Cross            → EMA(20) cruza por debajo de la EMA(50)
    2. Time-stop (80 velas)   → Válvula de seguridad

Sizing:
  Asume el riesgo por defecto implementado en el sistema a través del RiskManager,
  calculado por engine automáticamente usando ATR(14).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from signal_provider import SignalProvider


class EMACrossoverStrategy(SignalProvider):
    """
    Estrategia basada en cruces de EMA(20) y EMA(50).
    """

    def check_entry(
        self,
        fifo: deque,
        regime: MarketRegime,
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Evalúa si se cumplen todas las condiciones de entrada de EMA Crossover.
        """
        if len(fifo) < 2:
            return False

        # Solo operamos a favor de la tendencia principal (Precio > EMA200)
        if bullish_bias is not True:
            return False

        current = fifo[-1]
        previous = fifo[-2]

        if None in (current.ema_20, current.ema_50, previous.ema_20, previous.ema_50):
            return False

        # Golden Cross: EMA20 cruza por encima de EMA50
        if previous.ema_20 <= previous.ema_50 and current.ema_20 > current.ema_50:
            return True

        return False

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Evalúa si se debe cerrar la posición abierta.
        """
        if not fifo:
            return "TIME_STOP"

        # Válvula de seguridad de 80 velas
        if candles_held >= 80:
            return "TIME_STOP"

        if len(fifo) < 2:
            return None

        current = fifo[-1]
        previous = fifo[-2]

        if None in (current.ema_20, current.ema_50, previous.ema_20, previous.ema_50):
            return None

        # Death Cross: EMA20 cruza por debajo de EMA50
        if previous.ema_20 >= previous.ema_50 and current.ema_20 < current.ema_50:
            return "EMA_DEATH_CROSS"

        return None
