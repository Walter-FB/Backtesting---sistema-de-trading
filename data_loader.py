"""
data_loader.py — Cargador de Datos JSON para el Sistema de Trading
==================================================================
Lee archivos JSON con la estructura:
  {
    "meta": { "symbol": ..., "timeframe": ..., "candles": ... },
    "data": {
      "<unix_timestamp>": {
        "timestamp": int,
        "formatted_date": str,
        "ohlcv": { "open", "high", "low", "close", "volume_units", ... },
        "indicators": {
          "rsi": { "value": float },
          "macd": { "macd_line", "signal_line", "histogram" },
          "emas": { "ema_20", "ema_50", "ema_100", "ema_200", ... },
          "bollinger_bands": { "bb_mid", "bb_upper", "bb_lower", ... }
        }
      },
      ...
    }
  }

Retorna una List[Candle] ordenada cronológicamente.
Los indicadores calculados por el engine (rsi_2, sma_200, atr_14, adx_14)
quedan en None — el TradingEngine los completará sin look-ahead.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from models import Candle

logger = logging.getLogger(__name__)


class JSONDataLoader:
    """
    Cargador de datos de mercado desde archivos JSON.

    Métodos públicos
    ----------------
    load_from_json(file_path) -> List[Candle]
        Lee el JSON y retorna velas ordenadas por timestamp ascendente.

    Ejemplo de uso
    --------------
    >>> loader = JSONDataLoader()
    >>> candles = loader.load_from_json("Data_Leo/NASDAQ_COST/COST_1D_3000Bars.json")
    >>> print(f"Se cargaron {len(candles)} velas.")
    """

    def load_from_json(self, file_path: str) -> List[Candle]:
        """
        Lee un archivo JSON de mercado y retorna una lista de Candle
        ordenada cronológicamente (timestamp ascendente).

        Parámetros
        ----------
        file_path : str
            Ruta al archivo JSON (relativa o absoluta).

        Retorna
        -------
        List[Candle]
            Lista de velas ordenadas de más antigua a más reciente.

        Lanza
        -----
        FileNotFoundError : Si el archivo no existe.
        ValueError        : Si el JSON no tiene la estructura esperada.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {file_path}")

        logger.info(f"Cargando datos desde: {path.resolve()}")

        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # ── Validación de estructura ──────────────────────────────────────
        if "data" not in raw:
            raise ValueError(
                f"El JSON '{file_path}' no tiene la clave 'data' esperada."
            )

        meta = raw.get("meta", {})
        symbol = meta.get("symbol", "DESCONOCIDO")
        timeframe = meta.get("timeframe", "?")
        expected_count = meta.get("candles", "?")

        logger.info(
            f"Símbolo: {symbol} | Timeframe: {timeframe} | "
            f"Velas esperadas: {expected_count}"
        )

        candles: List[Candle] = []

        for ts_key, entry in raw["data"].items():
            try:
                candle = self._parse_entry(entry)
                candles.append(candle)
            except (KeyError, TypeError) as e:
                logger.warning(
                    f"Entrada {ts_key} omitida por error de parsing: {e}"
                )
                continue

        # ── Ordenamiento cronológico ascendente ───────────────────────────
        candles.sort(key=lambda c: c.timestamp)

        logger.info(
            f"Cargadas y ordenadas {len(candles)} velas para {symbol}."
        )
        return candles

    # ── Helpers privados ──────────────────────────────────────────────────

    @staticmethod
    def _parse_entry(entry: dict) -> Candle:
        """
        Transforma un diccionario del JSON en un objeto Candle.
        Los indicadores calculados (rsi_2, sma_200, atr_14, adx_14)
        se dejan en None intencionalmente.
        """
        ohlcv = entry["ohlcv"]
        indicators = entry.get("indicators", {})

        # ── RSI ──────────────────────────────────────────────────────────
        rsi_data = indicators.get("rsi", {})
        rsi: Optional[float] = rsi_data.get("value")

        # ── MACD ─────────────────────────────────────────────────────────
        macd_data = indicators.get("macd", {})
        macd_line: Optional[float] = macd_data.get("macd_line")
        signal_line: Optional[float] = macd_data.get("signal_line")
        macd_histogram: Optional[float] = macd_data.get("histogram")

        # ── EMAs ─────────────────────────────────────────────────────────
        emas_data = indicators.get("emas", {})
        ema_20: Optional[float] = emas_data.get("ema_20")
        ema_50: Optional[float] = emas_data.get("ema_50")
        ema_100: Optional[float] = emas_data.get("ema_100")
        ema_200: Optional[float] = emas_data.get("ema_200")

        # ── Bollinger Bands ───────────────────────────────────────────────
        bb_data = indicators.get("bollinger_bands", {})
        bb_mid: Optional[float] = bb_data.get("bb_mid")
        bb_upper: Optional[float] = bb_data.get("bb_upper")
        bb_lower: Optional[float] = bb_data.get("bb_lower")

        return Candle(
            # Temporalidad
            timestamp=entry["timestamp"],
            formatted_date=entry.get("formatted_date", ""),
            # OHLCV
            open=float(ohlcv["open"]),
            high=float(ohlcv["high"]),
            low=float(ohlcv["low"]),
            close=float(ohlcv["close"]),
            volume=float(ohlcv.get("volume_units", 0.0)),
            # Indicadores del proveedor
            rsi=rsi,
            macd_line=macd_line,
            signal_line=signal_line,
            macd_histogram=macd_histogram,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_100=ema_100,
            ema_200=ema_200,
            bb_mid=bb_mid,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            # Indicadores calculados: SIEMPRE None al cargar
            # pronostico_del_clima.py los completará sin look-ahead
            rsi_2=None,
            atr_14=None,
            adx_14=None,
        )
