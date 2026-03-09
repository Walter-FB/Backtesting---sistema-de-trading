"""
signal_provider.py — Contrato de Proveedor de Señales (Patrón Strategy)
========================================================================
Define la interfaz abstracta que todo proveedor de señales de trading
debe cumplir para poder conectarse al TradingEngine.

Patrón de diseño: Strategy + Dependency Injection
  - SignalProvider define el CONTRATO (qué métodos debe tener).
  - Cada implementación concreta (RSI2Strategy, EMACrossover, etc.)
    provee su propia lógica sin que el engine sepa nada de ella.
  - El TradingEngine recibe el proveedor inyectado en su __init__,
    lo que lo hace intercambiable sin tocar una sola línea del motor.

Cómo crear un nuevo proveedor de señales:
  1. Crear un archivo nuevo (ej: ema_crossover.py)
  2. Definir la clase heredando de SignalProvider:
       class EMACrossover(SignalProvider):
           def check_entry(self, fifo, regime, bullish_bias): ...
           def check_exit(self, fifo, candles_held): ...
  3. Pasarla al engine en tu runner:
       engine = TradingEngine(strategy=EMACrossover(), initial_balance=...)

Regla de oro: ningún proveedor accede a datos futuros.
  check_entry y check_exit solo pueden leer fifo[-1] y datos históricos
  dentro del buffer FIFO. Jamás data[i+1].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Optional

from analysis import MarketRegime


class SignalProvider(ABC):
    """
    Interfaz abstracta para todos los proveedores de señales del sistema.

    Métodos obligatorios
    --------------------
    check_entry(fifo, regime, bullish_bias) -> bool
        Evalúa si se debe abrir una posición Long al cierre de la vela actual.
        La ejecución ocurre al open del día siguiente (responsabilidad del engine).

    check_exit(fifo, candles_held) -> Optional[str]
        Evalúa si se debe cerrar la posición actualmente abierta.
        Retorna la razón de salida como string, o None para mantener.

    Garantías del sistema
    ---------------------
    - El engine llama a check_entry SOLO cuando no hay posición abierta.
    - El engine llama a check_exit SOLO cuando hay una posición abierta.
    - fifo siempre contiene al menos 1 elemento cuando se llama.
    - fifo[-1] es siempre la vela actual (la más reciente).
    """

    @abstractmethod
    def check_entry(
        self,
        fifo: deque,
        regime: MarketRegime,
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Evalúa las condiciones de entrada para abrir una posición Long.

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO (vela actual al final)
        regime       : MarketRegime  — régimen de mercado actual
        bullish_bias : Optional[bool]
                       True  → precio > EMA200 (alcista)
                       False → precio ≤ EMA200 (bajista)
                       None  → EMA200 no disponible aún

        Retorna
        -------
        bool
            True  → abrir posición al open de la vela siguiente
            False → no hay señal de entrada
        """
        ...

    @abstractmethod
    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Evalúa las condiciones de salida para cerrar la posición abierta.

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO (vela actual al final)
        candles_held : int — cantidad de velas desde la entrada

        Retorna
        -------
        str  → razón de salida (ej: "RSI_TARGET", "TIME_STOP", "EMA_CROSS")
        None → mantener la posición abierta
        """
        ...
