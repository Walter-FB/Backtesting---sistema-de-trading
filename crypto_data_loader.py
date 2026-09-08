"""
crypto_data_loader.py — Cargador de Datos Cripto (ccxt) con Cacheo a Disco
=============================================================================
Trae velas OHLCV históricas de un exchange cripto (Binance por defecto,
cualquier exchange soportado por ccxt en general), calcula los mismos
indicadores "de proveedor" que ya vienen precargados en los JSON de
Data_Leo/ (EMA20/50/100/200, RSI(14), MACD, Bandas de Bollinger) y los
guarda en el MISMO formato JSON que usa data_loader.JSONDataLoader.

Por qué el mismo formato
--------------------------
Así los datos cripto quedan como un ciudadano de primera clase del sistema:
cualquier módulo que ya sabe leer Data_Leo/ (engine.py, _test_run.py) puede
leer Data_Cripto/ sin cambios. No se inventa un formato nuevo.

Por qué se cachea a disco
----------------------------
Bajar 10 años de velas de varios pares es lento (rate limit del exchange) y
además esta sesión puede correr en un entorno con salida de red restringida.
Una vez descargado, fetch_and_cache() reutiliza el JSON cacheado — solo
vuelve a pegarle al exchange si no existe el archivo o si force_refresh=True.

Los indicadores "de provincia" (ema_20/50/100/200, rsi, macd, bb) se calculan
UNA vez sobre toda la serie histórica, de forma incremental (cada valor usa
solo datos hasta ese punto) — es equivalente a como si el exchange los
hubiese provisto ya calculados; no viola la regla de "sin look-ahead".

Los indicadores que el ENGINE calcula en tiempo real desde el buffer FIFO
(rsi_2, atr_14, adx_14) NO se tocan acá — data_loader los deja en None y
pronostico_del_clima.py los completa durante el backtest, igual que con
los datos de acciones.

Requiere: pip install ccxt

Uso
---
    from crypto_data_loader import CryptoDataLoader

    loader = CryptoDataLoader(exchange_id="binance")
    candles = loader.fetch_and_cache("BTC/USDT", timeframe="1d", years=10)
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from data_loader import JSONDataLoader
from models import Candle

logger = logging.getLogger(__name__)


class CryptoDataLoader:
    """
    Cargador de velas cripto desde un exchange soportado por ccxt, con
    cacheo a disco en el formato JSON compatible con data_loader.JSONDataLoader.

    Métodos públicos
    ----------------
    load_ohlcv(symbol, timeframe, since_ms, max_candles) -> List[Candle]
        Descarga velas históricas (paginando si hace falta) y las enriquece
        con EMA/RSI/MACD/BB. No cachea — siempre pega al exchange.

    fetch_and_cache(symbol, timeframe, years, cache_dir, force_refresh) -> List[Candle]
        Igual que load_ohlcv, pero reutiliza el JSON cacheado si ya existe.
        Es el método recomendado para pasadas repetidas de backtest.
    """

    def __init__(self, exchange_id: str = "binance") -> None:
        try:
            import ccxt
        except ImportError as e:
            raise ImportError(
                "Falta instalar 'ccxt': pip install ccxt"
            ) from e

        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({"enableRateLimit": True})
        self.exchange_id = exchange_id

    # ── Descarga cruda (sin cache) ────────────────────────────────────────────

    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        since_ms: Optional[int] = None,
        max_candles: Optional[int] = None,
        page_limit: int = 1000,
    ) -> List[Candle]:
        """
        Descarga velas OHLCV (paginando si hace falta) y las convierte a
        List[Candle] ordenada cronológicamente, con EMA/RSI/MACD/BB calculados.

        Parámetros
        ----------
        symbol      : str — par en formato ccxt (ej: "BTC/USDT")
        timeframe   : str — "1m", "5m", "15m", "1h", "4h", "1d", etc.
        since_ms    : Optional[int] — timestamp ms desde donde empezar
                      (None = lo más viejo que el exchange tenga disponible)
        max_candles : Optional[int] — tope total de velas a juntar (pagina hasta llegar)
        page_limit  : int — velas por request (tope del exchange; Binance = 1000)

        Retorna
        -------
        List[Candle] ordenada de más antigua a más reciente.
        """
        logger.info(f"Descargando {symbol} {timeframe} desde {self.exchange_id}...")

        raw_rows: List[list] = []
        cursor = since_ms

        while True:
            batch = self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=cursor, limit=page_limit
            )
            if not batch:
                break
            raw_rows.extend(batch)

            if max_candles is not None and len(raw_rows) >= max_candles:
                break

            last_ts = batch[-1][0]
            if cursor is not None and last_ts <= cursor:
                break  # el exchange no avanzó — evitar loop infinito
            cursor = last_ts + 1

            if len(batch) < page_limit:
                break  # última página parcial — no hay más datos

        if max_candles is not None:
            raw_rows = raw_rows[-max_candles:]

        logger.info(f"{len(raw_rows)} velas descargadas para {symbol} {timeframe}.")

        candles = [_row_to_candle(row) for row in raw_rows]
        candles.sort(key=lambda c: c.timestamp)
        _enrich_provider_indicators(candles)
        return candles

    # ── Descarga con cacheo a disco ───────────────────────────────────────────

    def fetch_and_cache(
        self,
        symbol: str,
        timeframe: str = "1d",
        years: int = 10,
        cache_dir: str = "Data_Cripto",
        force_refresh: bool = False,
        max_candles: Optional[int] = None,
    ) -> List[Candle]:
        """
        Trae velas históricas de `years` años para `symbol`, reutilizando
        el JSON cacheado en disco si ya existe (a menos que force_refresh=True).

        Parámetros
        ----------
        symbol        : str — par en formato ccxt (ej: "BTC/USDT")
        timeframe     : str — timeframe ccxt (ej: "1d", "4h", "1h")
        years         : int — años de historial a pedir hacia atrás desde hoy
        cache_dir     : str — carpeta raíz donde se guarda/lee el cache
        force_refresh : bool — si True, ignora el cache y vuelve a descargar
        max_candles   : Optional[int] — tope total de velas (None = todas las disponibles)

        Retorna
        -------
        List[Candle] ordenada cronológicamente, lista para pasarle a TradingEngine.
        """
        path = _cache_path(cache_dir, self.exchange_id, symbol, timeframe, years)

        if not force_refresh and os.path.exists(path):
            logger.info(f"Cache encontrado para {symbol} {timeframe} ({years}y): {path}")
            return JSONDataLoader().load_from_json(path)

        since_ms = int(
            (datetime.now(timezone.utc) - timedelta(days=365 * years)).timestamp() * 1000
        )
        candles = self.load_ohlcv(symbol, timeframe=timeframe, since_ms=since_ms, max_candles=max_candles)

        if candles:
            _save_candles_as_json(candles, symbol=symbol, timeframe=timeframe, path=path)
            logger.info(f"Cache guardado: {path}")

        return candles


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS: conversión de filas ccxt y ruta de cache
# ═══════════════════════════════════════════════════════════════════════════════

def _row_to_candle(row: list) -> Candle:
    """Convierte una fila ccxt [timestamp_ms, open, high, low, close, volume] a Candle."""
    ts_ms, o, h, l, c, v = row
    ts_s = int(ts_ms // 1000)
    formatted = datetime.fromtimestamp(ts_s, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return Candle(
        timestamp=ts_s,
        formatted_date=formatted,
        open=float(o), high=float(h), low=float(l), close=float(c),
        volume=float(v or 0.0),
    )


def _sanitize_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTC_USDT' — seguro para nombres de archivo/carpeta."""
    return symbol.replace("/", "_").replace(":", "_")


def _cache_path(cache_dir: str, exchange_id: str, symbol: str, timeframe: str, years: int) -> str:
    safe_symbol = _sanitize_symbol(symbol)
    folder = os.path.join(cache_dir, exchange_id, timeframe, safe_symbol)
    filename = f"{safe_symbol}_{timeframe}_{years}Y.json"
    return os.path.join(folder, filename)


# ═══════════════════════════════════════════════════════════════════════════════
# GUARDADO EN FORMATO JSON COMPATIBLE CON data_loader.JSONDataLoader
# ═══════════════════════════════════════════════════════════════════════════════

def _save_candles_as_json(candles: List[Candle], symbol: str, timeframe: str, path: str) -> None:
    """
    Serializa la lista de Candle al mismo esquema JSON que usan los archivos
    de Data_Leo/, para que JSONDataLoader.load_from_json() los pueda leer
    de vuelta sin ningún cambio.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {}
    for c in candles:
        data[str(c.timestamp)] = {
            "timestamp": c.timestamp,
            "formatted_date": c.formatted_date,
            "ohlcv": {
                "open": c.open, "high": c.high, "low": c.low, "close": c.close,
                "volume_units": c.volume,
            },
            "indicators": {
                "rsi": {"value": c.rsi},
                "macd": {
                    "macd_line": c.macd_line,
                    "signal_line": c.signal_line,
                    "histogram": c.macd_histogram,
                },
                "emas": {
                    "ema_20": c.ema_20, "ema_50": c.ema_50,
                    "ema_100": c.ema_100, "ema_200": c.ema_200,
                },
                "bollinger_bands": {
                    "bb_mid": c.bb_mid, "bb_upper": c.bb_upper, "bb_lower": c.bb_lower,
                },
            },
        }

    payload = {
        "meta": {"symbol": symbol, "timeframe": timeframe, "candles": len(candles)},
        "data": data,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


# ═══════════════════════════════════════════════════════════════════════════════
# ENRIQUECIMIENTO: indicadores "de proveedor" calculados sobre toda la serie
# ═══════════════════════════════════════════════════════════════════════════════

def _enrich_provider_indicators(candles: List[Candle]) -> None:
    """
    Calcula EMA(20/50/100/200), RSI(14), MACD(12,26,9) y Bandas de
    Bollinger(20,2) de forma incremental sobre la serie completa y los
    escribe en cada Candle.

    Cada valor en el índice i se calcula usando SOLO candles[0..i] — es
    exactamente lo que un proveedor de datos real entrega (indicadores ya
    calculados históricamente), y respeta la regla de no look-ahead.
    """
    n = len(candles)
    if n == 0:
        return

    closes = [c.close for c in candles]

    for period in (20, 50, 100, 200):
        _apply_ema_series(candles, closes, period)

    _apply_rsi_series(candles, closes, period=14)
    _apply_macd_series(candles, closes, fast=12, slow=26, signal=9)
    _apply_bollinger_series(candles, closes, period=20, num_std=2.0)


def _apply_ema_series(candles: List[Candle], closes: List[float], period: int) -> None:
    attr = f"ema_{period}"
    n = len(closes)
    if n < period:
        return
    k = 2.0 / (period + 1)
    ema_val = sum(closes[:period]) / period
    setattr(candles[period - 1], attr, ema_val)
    for i in range(period, n):
        ema_val = closes[i] * k + ema_val * (1 - k)
        setattr(candles[i], attr, ema_val)


def _apply_rsi_series(candles: List[Candle], closes: List[float], period: int) -> None:
    n = len(closes)
    if n < period + 1:
        return

    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)

    avg_gain = gains / period
    avg_loss = losses / period

    def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    candles[period].rsi = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period + 1, n):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        candles[i].rsi = _rsi_from_avgs(avg_gain, avg_loss)


def _apply_macd_series(
    candles: List[Candle], closes: List[float], fast: int, slow: int, signal: int
) -> None:
    n = len(closes)
    if n < slow:
        return

    def _ema_incremental(period: int) -> List[Optional[float]]:
        out: List[Optional[float]] = [None] * n
        if n < period:
            return out
        k = 2.0 / (period + 1)
        val = sum(closes[:period]) / period
        out[period - 1] = val
        for i in range(period, n):
            val = closes[i] * k + val * (1 - k)
            out[i] = val
        return out

    ema_fast = _ema_incremental(fast)
    ema_slow = _ema_incremental(slow)

    macd_line_series: List[Optional[float]] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]

    first_valid = next((i for i, v in enumerate(macd_line_series) if v is not None), None)
    if first_valid is None:
        return

    valid_macd = macd_line_series[first_valid:]
    if len(valid_macd) < signal:
        return

    k_signal = 2.0 / (signal + 1)
    signal_val = sum(valid_macd[:signal]) / signal
    signal_series: List[Optional[float]] = [None] * n
    signal_series[first_valid + signal - 1] = signal_val

    for offset in range(signal, len(valid_macd)):
        i = first_valid + offset
        signal_val = valid_macd[offset] * k_signal + signal_val * (1 - k_signal)
        signal_series[i] = signal_val

    for i in range(n):
        candles[i].macd_line = macd_line_series[i]
        candles[i].signal_line = signal_series[i]
        if macd_line_series[i] is not None and signal_series[i] is not None:
            candles[i].macd_histogram = macd_line_series[i] - signal_series[i]


def _apply_bollinger_series(
    candles: List[Candle], closes: List[float], period: int, num_std: float
) -> None:
    n = len(closes)
    if n < period:
        return
    window: deque = deque(maxlen=period)
    for i in range(n):
        window.append(closes[i])
        if len(window) < period:
            continue
        mid = sum(window) / period
        variance = sum((v - mid) ** 2 for v in window) / period
        std_dev = variance ** 0.5
        candles[i].bb_mid = mid
        candles[i].bb_upper = mid + num_std * std_dev
        candles[i].bb_lower = mid - num_std * std_dev
