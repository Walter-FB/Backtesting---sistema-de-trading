"""
strategy_factory.py — Descubrimiento y Creación de Estrategias
================================================================
Punto único de creación de estrategias. El runner, el dashboard y cualquier
otro módulo solo necesitan saber el NOMBRE de la estrategia.

Auto-descubrimiento
--------------------
No hay registro manual. Cada archivo .py dentro de Strategys_Backtesting/
que defina una subclase de SignalProvider se registra solo, con el nombre
del archivo como clave:

    Strategys_Backtesting/triple_ema.py   →   "triple_ema"

Para agregar una estrategia alcanza con soltar el archivo en la carpeta.
Los archivos cuyo nombre empieza con guión bajo (como _plantilla.py) se
ignoran a propósito.

Uso:
    from strategy_factory import StrategyFactory

    StrategyFactory.available_strategies()          # ['connors_rsi2', 'triple_ema', ...]
    StrategyFactory.create("triple_ema")            # con sus parámetros por defecto
    StrategyFactory.create("tp_sl_fijo", take_profit_pct=3.0, stop_loss_pct=1.5)
    StrategyFactory.parametros_de("tp_sl_fijo")     # qué perillas tiene, para armar la UI
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any, Dict, Type

import Strategys_Backtesting as _paquete
from signal_provider import SignalProvider


def _descubrir() -> Dict[str, Type[SignalProvider]]:
    registro: Dict[str, Type[SignalProvider]] = {}

    for info in pkgutil.iter_modules(_paquete.__path__):
        if info.name.startswith("_"):
            continue

        modulo = importlib.import_module(f"{_paquete.__name__}.{info.name}")

        # Solo las clases DEFINIDAS en ese archivo: las importadas de otro
        # lado (SignalProvider mismo, o una estrategia base) no cuentan.
        clases = [
            obj for _, obj in inspect.getmembers(modulo, inspect.isclass)
            if issubclass(obj, SignalProvider)
            and obj is not SignalProvider
            and obj.__module__ == modulo.__name__
        ]

        if not clases:
            continue
        if len(clases) > 1:
            raise ValueError(
                f"{info.name}.py define más de una estrategia "
                f"({[c.__name__ for c in clases]}). Una por archivo, así el "
                f"nombre del archivo identifica a la estrategia sin ambigüedad."
            )

        registro[info.name] = clases[0]

    return registro


STRATEGY_REGISTRY: Dict[str, Type[SignalProvider]] = _descubrir()


class StrategyFactory:
    """
    Descubridor y creador de estrategias de trading.

    Métodos
    -------
    create(name, **params)   → SignalProvider instanciado y listo para inyectar
    available_strategies()   → lista de nombres descubiertos
    parametros_de(name)      → declaración de parámetros ajustables (para la UI)
    clase_de(name)           → la clase, por si hace falta inspeccionarla
    """

    @staticmethod
    def clase_de(name: str) -> Type[SignalProvider]:
        clase = STRATEGY_REGISTRY.get(name)
        if clase is None:
            raise ValueError(
                f"Estrategia desconocida: '{name}'\n"
                f"Disponibles: {sorted(STRATEGY_REGISTRY)}\n"
                f"Para agregar una, soltá un .py en Strategys_Backtesting/ que "
                f"defina una subclase de SignalProvider."
            )
        return clase

    @staticmethod
    def create(name: str, **params: Any) -> SignalProvider:
        """
        Instancia la estrategia `name`. Los `params` sobreescriben los valores
        por defecto declarados en su PARAMETROS; un nombre no declarado es error.
        """
        return StrategyFactory.clase_de(name)(**params)

    @staticmethod
    def parametros_de(name: str) -> Dict[str, Dict[str, Any]]:
        """Declaración de parámetros ajustables de la estrategia (puede ser vacía)."""
        return dict(StrategyFactory.clase_de(name).PARAMETROS)

    @staticmethod
    def available_strategies() -> list[str]:
        return sorted(STRATEGY_REGISTRY)
