"""
signal_provider.py — Contrato de Proveedor de Señales (Patrón Strategy)
========================================================================
Define la interfaz abstracta que toda estrategia debe cumplir para poder
conectarse al TradingEngine.

Patrón de diseño: Strategy + Dependency Injection
  - SignalProvider define el CONTRATO (qué métodos debe tener).
  - Cada implementación concreta provee su propia lógica sin que el engine
    sepa nada de ella.
  - El TradingEngine recibe la estrategia inyectada en su __init__, lo que
    la hace intercambiable sin tocar una sola línea del motor.

Cómo crear una estrategia nueva
--------------------------------
  1. Copiá Strategys_Backtesting/_plantilla.py con otro nombre dentro de la
     misma carpeta (ej. mi_estrategia.py).
  2. Implementá check_entry y check_exit.
  3. Listo. El sistema la descubre sola por el nombre del archivo — no hay
     que registrarla en ningún lado.

Parámetros ajustables
----------------------
Si querés que tu estrategia tenga perillas (un take profit, un umbral de
RSI, lo que sea) que se puedan cambiar desde el dashboard o desde el
código sin editar el archivo, declaralas en el atributo de clase
PARAMETROS:

    class MiEstrategia(SignalProvider):
        PARAMETROS = {
            "rsi_entrada": {"default": 30.0, "min": 5.0, "max": 50.0, "step": 1.0,
                            "ayuda": "RSI por debajo del cual se compra"},
            "time_stop":   {"default": 20,   "min": 1,   "max": 200,  "step": 1},
        }

        def check_entry(self, fifo, regime, bullish_bias):
            if rsi(fifo, 14) < self.p["rsi_entrada"]:
                ...

Los valores quedan en `self.p`, ya mezclados con los que pase quien la
instancie: MiEstrategia() usa los defaults, MiEstrategia(rsi_entrada=25)
sobreescribe uno. Pasar un nombre que no está declarado es un error,
para que un typo no se convierta en un parámetro que no hace nada.

Regla de oro: ningún proveedor accede a datos futuros.
  check_entry y check_exit solo pueden leer fifo[-1] y datos históricos
  dentro del buffer FIFO. Jamás data[i+1].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Dict, Optional

from analysis import MarketRegime


class SignalProvider(ABC):
    """
    Interfaz abstracta para todos los proveedores de señales del sistema.

    Métodos obligatorios
    --------------------
    check_entry(fifo, regime, bullish_bias) -> bool
        Evalúa si se debe abrir una posición Long al cierre de la vela actual.
        La ejecución ocurre al open de la vela siguiente (responsabilidad del engine).

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

    # Declaración de parámetros ajustables. Vacío = la estrategia no tiene perillas.
    PARAMETROS: Dict[str, Dict[str, Any]] = {}

    def __init__(self, **overrides: Any) -> None:
        desconocidos = set(overrides) - set(self.PARAMETROS)
        if desconocidos:
            raise ValueError(
                f"{type(self).__name__} no declara los parámetros {sorted(desconocidos)}. "
                f"Los que acepta son: {sorted(self.PARAMETROS) or 'ninguno'}"
            )
        self.p: Dict[str, Any] = {
            nombre: spec["default"] for nombre, spec in self.PARAMETROS.items()
        }
        self.p.update(overrides)

    @abstractmethod
    def check_entry(
        self,
        fifo: deque,
        regime: Optional[MarketRegime],
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Evalúa las condiciones de entrada para abrir una posición Long.

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO (vela actual al final)
        regime       : clima clásico como Enum, o None si el pronóstico activo
                       no usa el vocabulario clásico
        bullish_bias : True → precio > EMA200 | False → precio ≤ EMA200 | None → sin dato

        Retorna True para abrir posición al open de la vela siguiente.
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
        candles_held : velas transcurridas desde la entrada (vale 1 en la vela de entrada)

        Retorna la razón de salida (ej: "TAKE_PROFIT", "TIME_STOP") o None para mantener.
        El texto aparece agrupado en los reportes: usá nombres que sirvan para diagnosticar.
        """
        ...
