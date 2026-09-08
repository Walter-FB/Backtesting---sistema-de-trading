"""
Climas_Backtesting — Pronósticos de Clima del Sistema
========================================================
Cada archivo de este paquete es un ClimateProvider concreto (hereda de
climate_provider.ClimateProvider). Es el espejo exacto de Strategys_Backtesting/,
pero para detectores de régimen/clima en vez de estrategias de entrada/salida.

Para agregar un pronóstico de clima nuevo:
  1. Crear el archivo acá heredando de ClimateProvider
  2. Implementar detect(fifo) -> ClimateReading
  3. Registrarlo en climate_factory.py (CLIMATE_REGISTRY)
"""
