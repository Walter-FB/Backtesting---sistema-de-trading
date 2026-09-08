"""
multi_timeframe.py — Clima leído en un Timeframe Superior (HTF)
==================================================================
Permite operar en un timeframe rápido (ej. velas de 1m) mientras el
pronóstico del clima se lee en un timeframe lento (ej. velas diarias).

El caso de uso: el sistema ejecuta en 1m, pero "qué estación del año es"
(criptoinvierno, tendencia alcista, lateral) es una pregunta estructural
que no tiene sentido responder mirando una vela de un minuto.

LA TRAMPA QUE ESTO EVITA (leer esto antes de tocar el archivo)
---------------------------------------------------------------
Estar parado en la vela de 1m del día 5 a las 10:00 y consultar "el clima
diario de hoy" es LOOK-AHEAD: la vela diaria del día 5 todavía se está
formando — su cierre, su máximo y su mínimo aún no existen. Usarla sería
leer el futuro, y es una de las formas más comunes (y más silenciosas) de
inflar los resultados de un backtest multi-timeframe.

La regla que aplica este módulo: una vela HTF solo entra al buffer cuando
YA CERRÓ, es decir cuando

    vela_htf.timestamp + duración_del_timeframe  <=  timestamp_actual

Parado en cualquier momento del día 5, el clima disponible es el que
resulta de las velas diarias hasta el día 4 inclusive. Ni una más.

Por qué esto no toca el engine
-------------------------------
Es un ClimateProvider más: cumple el mismo contrato que cualquier otro
(detect(fifo) -> ClimateReading). El engine sigue iterando velas de 1m sin
enterarse de nada — toda la alineación entre timeframes vive acá adentro.

Uso
---
    from crypto_data_loader import CryptoDataLoader
    from Climas_Backtesting.multi_timeframe import MultiTimeframeClimate

    loader  = CryptoDataLoader()
    velas_1m = loader.fetch_and_cache("BTC/USDT", timeframe="1m", years=1)
    velas_1d = loader.fetch_and_cache("BTC/USDT", timeframe="1d", years=10)

    engine = TradingEngine(
        strategy         = StrategyFactory.create("mi_estrategia"),
        climate_provider = MultiTimeframeClimate(velas_1d, htf_timeframe="1d"),
    )
    engine.run_backtest(velas_1m, ticker="BTC_USDT")
"""

from __future__ import annotations

import re
from collections import deque
from typing import List, Optional

from analysis import MarketRegime
from climate_provider import ClimateProvider, ClimateReading
from Climas_Backtesting.clasico_adx_ema200 import ClassicRegimeClimate
from models import Candle
from pronostico_del_clima import compute_and_set_indicators

# Cuántas velas HTF mantiene el buffer interno. 250 velas diarias ≈ 1 año.
HTF_BUFFER_LEN: int = 250

_TIMEFRAME_UNITS = {"m": 60, "h": 3_600, "d": 86_400, "w": 604_800}


def timeframe_to_seconds(timeframe: str) -> int:
    """
    Convierte un timeframe estilo ccxt a segundos: "1m" → 60, "4h" → 14400,
    "1d" → 86400.

    Lanza ValueError si el formato no se reconoce.
    """
    match = re.fullmatch(r"(\d+)([mhdw])", timeframe.strip().lower())
    if not match:
        raise ValueError(
            f"Timeframe no reconocido: '{timeframe}'. "
            f"Usá formato tipo '1m', '15m', '4h', '1d'."
        )
    amount, unit = match.groups()
    return int(amount) * _TIMEFRAME_UNITS[unit]


class MultiTimeframeClimate(ClimateProvider):
    """
    Lee el clima en un timeframe superior al de ejecución, respetando el
    cierre real de cada vela HTF (sin look-ahead entre timeframes).

    Parámetros
    ----------
    htf_candles   : List[Candle] — velas del timeframe superior, ordenadas
                    cronológicamente y ya enriquecidas con los indicadores
                    del proveedor (ema_200 etc.), tal como las devuelve
                    CryptoDataLoader o JSONDataLoader.
    htf_timeframe : str — timeframe de esas velas ("1d", "4h", "12h"...).
                    Se usa para saber cuándo cierra cada una.
    inner         : ClimateProvider — el pronóstico que se aplica SOBRE las
                    velas HTF. Por defecto el clásico (ADX + EMA200), pero
                    puede ser cualquiera: así un clima propio tuyo se puede
                    leer en diaria sin escribir nada nuevo.
    buffer_len    : int — cuántas velas HTF mantener en el buffer interno.
    """

    def __init__(
        self,
        htf_candles: List[Candle],
        htf_timeframe: str,
        inner: Optional[ClimateProvider] = None,
        buffer_len: int = HTF_BUFFER_LEN,
    ) -> None:
        self._htf_candles: List[Candle] = sorted(htf_candles, key=lambda c: c.timestamp)
        self._htf_timeframe: str = htf_timeframe
        self._htf_seconds: int = timeframe_to_seconds(htf_timeframe)
        self._inner: ClimateProvider = inner or ClassicRegimeClimate()

        self._htf_buffer: deque = deque(maxlen=buffer_len)
        self._cursor: int = 0   # próxima vela HTF candidata a entrar al buffer

        self._last_reading: ClimateReading = ClimateReading(
            label=MarketRegime.WAITING_FOR_DATA.name,
            regime=MarketRegime.WAITING_FOR_DATA,
        )

    def detect(self, fifo: deque) -> ClimateReading:
        """
        Avanza el buffer HTF hasta la última vela que YA CERRÓ en o antes del
        momento de la vela actual, y delega la clasificación al pronóstico
        interno.

        Entre cierres de vela HTF el clima no cambia: se devuelve la última
        lectura válida (que es exactamente lo que pasaría operando en vivo).
        """
        if not fifo:
            return self._last_reading

        now_ts = fifo[-1].timestamp

        while self._cursor < len(self._htf_candles):
            htf_candle = self._htf_candles[self._cursor]
            closes_at = htf_candle.timestamp + self._htf_seconds

            # Todavía no cerró: usarla sería leer el futuro. Cortamos acá.
            if closes_at > now_ts:
                break

            # Cada vela HTF se procesa exactamente una vez y en orden, para que
            # el pronóstico interno vea la misma secuencia que vería corriendo
            # solo sobre el timeframe superior (su estado interno queda intacto).
            self._htf_buffer.append(htf_candle)
            compute_and_set_indicators(self._htf_buffer)
            self._last_reading = self._inner.detect(self._htf_buffer)
            self._last_reading.details.update({
                "htf_timeframe":  self._htf_timeframe,
                "htf_last_date":  htf_candle.formatted_date,
                "htf_last_close_ts": closes_at,
            })
            self._cursor += 1

        return self._last_reading
