"""
climate_factory.py — Registro Central de Pronósticos de Clima (Patrón Factory)
=================================================================================
Punto único de creación de pronósticos de clima. Espejo exacto de
strategy_factory.py, para el lado del clima.

Cómo agregar un pronóstico de clima nuevo:
  1. Crear el archivo en Climas_Backtesting/ heredando de ClimateProvider
  2. Importarlo acá
  3. Agregar una entrada en CLIMATE_REGISTRY

Uso:
  from climate_factory import ClimateFactory
  engine = TradingEngine(strategy=..., climate_provider=ClimateFactory.create("clasico_adx_ema200"))
"""

from __future__ import annotations

from climate_provider import ClimateProvider

# ── Imports de climas disponibles ─────────────────────────────────────────────
from Climas_Backtesting.clasico_adx_ema200 import ClassicRegimeClimate
from Climas_Backtesting.sin_clima import NullClimateProvider


# ── Registro de climas ────────────────────────────────────────────────────────
CLIMATE_REGISTRY: dict[str, type[ClimateProvider]] = {
    "clasico_adx_ema200": ClassicRegimeClimate,
    "sin_clima":          NullClimateProvider,
}

# MultiTimeframeClimate (leer el clima en diaria mientras se opera en 1m) no
# entra en este registro porque necesita las velas del timeframe superior en
# su constructor. Se construye a mano y se le pasa al engine igual que
# cualquier otro clima — ver GUIA.md § 8.

DEFAULT_CLIMATE: str = "clasico_adx_ema200"


class ClimateFactory:
    """
    Registro central y creador de pronósticos de clima del sistema.

    Métodos
    -------
    create(name)         → ClimateProvider instanciado y listo para inyectar
    available_climates() → lista de nombres registrados
    """

    @staticmethod
    def create(name: str = DEFAULT_CLIMATE) -> ClimateProvider:
        """
        Instancia y retorna el pronóstico de clima correspondiente al nombre dado.

        Parámetros
        ----------
        name : str — clave del CLIMATE_REGISTRY (ej: "clasico_adx_ema200")

        Retorna
        -------
        ClimateProvider — instancia lista para pasar al TradingEngine

        Lanza
        -----
        ValueError si el nombre no está registrado.
        """
        climate_class = CLIMATE_REGISTRY.get(name)

        if climate_class is None:
            available = list(CLIMATE_REGISTRY.keys())
            raise ValueError(
                f"Pronóstico de clima desconocido: '{name}'\n"
                f"Disponibles: {available}\n"
                f"Agregá el nuevo en CLIMATE_REGISTRY dentro de climate_factory.py"
            )

        return climate_class()

    @staticmethod
    def available_climates() -> list[str]:
        """Retorna la lista de nombres de climas registrados."""
        return list(CLIMATE_REGISTRY.keys())
