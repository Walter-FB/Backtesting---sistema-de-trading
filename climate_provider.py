"""
climate_provider.py — Contrato de Pronóstico del Clima (Patrón Strategy)
==========================================================================
Define la interfaz abstracta que todo "pronóstico del clima" (detector de
régimen de mercado) debe cumplir para conectarse al TradingEngine.

Espejo exacto de signal_provider.py, pero para el lado del CLIMA en vez del
lado de la ESTRATEGIA:

  signal_provider.py   → contrato de estrategias  (Strategys_Backtesting/)
  climate_provider.py  → contrato de climas        (Climas_Backtesting/)   ← ESTE ARCHIVO

Por qué existe esto
--------------------
El sistema original tenía UN solo detector de régimen (ADX + EMA200) fijo
al enum MarketRegime de 5 estados. Esta capa lo generaliza: cualquier
ClimateProvider puede definir su propio vocabulario de climas (ej. un
"criptoinvierno" o cualquier otro concepto que no encaje en los 5 estados
clásicos), sin tocar el engine ni las estrategias existentes.

El engine sigue funcionando con el clima clásico por defecto — este archivo
solo define el contrato, no cambia el comportamiento de nadie.

Cómo crear un pronóstico de clima nuevo:
  1. Crear un archivo en Climas_Backtesting/ heredando de ClimateProvider
  2. Implementar detect(fifo) -> ClimateReading
  3. Registrarlo en climate_factory.py (una línea en CLIMATE_REGISTRY)

Regla de oro: igual que con las estrategias, ningún ClimateProvider accede
a datos futuros. detect() solo puede leer fifo[-1] y el historial dentro
del buffer FIFO.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from analysis import MarketRegime


@dataclass
class ClimateReading:
    """
    Lectura de clima de mercado en un momento dado (una vela).

    Campos
    ------
    label        : str — etiqueta del clima detectado. Vocabulario ABIERTO:
                   puede ser uno de los 5 estados clásicos de MarketRegime
                   (ej. "RANGING_MEAN_REVERSION") o cualquier nombre nuevo
                   que defina un ClimateProvider propio (ej. "CRIPTOINVIERNO").
    bullish_bias : Optional[bool] — sesgo direccional, si el clima lo define.
                   True → alcista | False → bajista | None → sin sesgo/N-A.
    confidence   : Optional[float] — confianza de la lectura (0–1), opcional.
    regime       : Optional[MarketRegime] — SOLO para compatibilidad con
                   estrategias existentes que comparan contra el Enum clásico
                   (ej. `if regime == MarketRegime.TRENDING_BULLISH`).
                   Los climas nuevos que no mapeen a un estado clásico dejan
                   esto en None — las estrategias que dependan del Enum
                   simplemente no encontrarán señal bajo ese clima (no rompen).
    details      : dict — cualquier dato extra del clima (ADX, métricas propias
                   de un pronóstico custom, etc.) para debugging/reportes.
    """
    label: str
    bullish_bias: Optional[bool] = None
    confidence: Optional[float] = None
    regime: Optional[MarketRegime] = None
    details: dict = field(default_factory=dict)


class ClimateProvider(ABC):
    """
    Interfaz abstracta para todo pronóstico de clima del sistema.

    Método obligatorio
    -------------------
    detect(fifo) -> ClimateReading
        Analiza el buffer FIFO en su estado actual y retorna la lectura
        de clima vigente para la vela actual (fifo[-1]).

    Garantías del sistema
    ----------------------
    - El engine llama a detect() UNA vez por vela, antes de evaluar la estrategia.
    - fifo siempre contiene al menos 1 elemento cuando se llama.
    - fifo[-1] es siempre la vela actual (la más reciente).
    """

    @abstractmethod
    def detect(self, fifo: deque) -> ClimateReading:
        """
        Evalúa el clima de mercado actual a partir del buffer FIFO.

        Parámetros
        ----------
        fifo : deque[Candle] — buffer FIFO (vela actual al final)

        Retorna
        -------
        ClimateReading — lectura de clima vigente para la vela actual.
        """
        ...
