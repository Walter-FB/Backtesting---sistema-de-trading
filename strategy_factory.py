"""
strategy_factory.py — Registro Central de Estrategias (Patrón Factory)
=======================================================================
Punto único de creación de estrategias. El runner y cualquier otro módulo
solo necesitan saber el NOMBRE de la estrategia, no su clase ni su módulo.

Patrón de diseño: Factory Method
  - StrategyFactory.create(name) devuelve un SignalProvider listo para usar.
  - Agregar una estrategia nueva = una línea en STRATEGY_REGISTRY.
  - El engine nunca sabe qué clase concreta está usando.

Cómo agregar una estrategia nueva:
  1. Crear el archivo en Strategys_Backtesting/ heredando de SignalProvider
  2. Importarla acá
  3. Agregar una entrada en STRATEGY_REGISTRY

Uso:
  from strategy_factory import StrategyFactory
  engine = TradingEngine(strategy=StrategyFactory.create("momentum_breakout"), ...)
"""

from __future__ import annotations

from signal_provider import SignalProvider

# ── Imports de estrategias disponibles ────────────────────────────────────────
from Strategys_Backtesting.connors_rsi2 import RSI2Strategy
from Strategys_Backtesting.momentum_breakout import MomentumBreakoutStrategy
from Strategys_Backtesting.ema_crossover import EMACrossoverStrategy


# ── Registro de estrategias ───────────────────────────────────────────────────
# Clave   : nombre que se usa en _test_run.py (STRATEGY_NAME = "...")
# Valor   : clase concreta (no instancia — el factory la instancia)
STRATEGY_REGISTRY: dict[str, type[SignalProvider]] = {
    "connors_rsi2":       RSI2Strategy,
    "momentum_breakout":  MomentumBreakoutStrategy,
    "ema_crossover":      EMACrossoverStrategy,
}


class StrategyFactory:
    """
    Registro central y creador de estrategias de trading.

    Métodos
    -------
    create(name)          → SignalProvider instanciado y listo para inyectar
    available_strategies  → lista de nombres registrados
    """

    @staticmethod
    def create(name: str) -> SignalProvider:
        """
        Instancia y retorna la estrategia correspondiente al nombre dado.

        Parámetros
        ----------
        name : str — clave del STRATEGY_REGISTRY (ej: "momentum_breakout")

        Retorna
        -------
        SignalProvider — instancia lista para pasar al TradingEngine

        Lanza
        -----
        ValueError si el nombre no está registrado.
        """
        strategy_class = STRATEGY_REGISTRY.get(name)

        if strategy_class is None:
            available = list(STRATEGY_REGISTRY.keys())
            raise ValueError(
                f"Estrategia desconocida: '{name}'\n"
                f"Disponibles: {available}\n"
                f"Agregá la nueva clase en STRATEGY_REGISTRY dentro de strategy_factory.py"
            )

        return strategy_class()

    @staticmethod
    def available_strategies() -> list[str]:
        """Retorna la lista de nombres de estrategias registradas."""
        return list(STRATEGY_REGISTRY.keys())
