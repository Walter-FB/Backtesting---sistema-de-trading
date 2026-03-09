"""
models.py — Modelo de Datos del Sistema de Trading Algorítmico
==============================================================
Define la clase Candle (vela OHLCV + indicadores), unidad fundamental
de información en todo el sistema.

Filosofía de diseño:
  - Los campos OHLCV y los indicadores del JSON se mapean 1:1 al cargar.
  - Los indicadores calculados (rsi_2, atr_14, adx_14) se inicializan
    en None y pronostico_del_clima.py los completa en cada paso del backtest,
    SÓLO con datos del FIFO buffer (sin look-ahead bias).
  - Los indicadores del proveedor (rsi, macd, emas, bb) se usan directamente
    tal como vienen del JSON — más precisos que cualquier recálculo local.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Candle:
    """
    Representa una vela de mercado con sus datos OHLCV e indicadores.

    Campos provenientes del JSON (proveedor)
    -----------------------------------------
    timestamp       : Unix timestamp (entero)
    formatted_date  : Fecha legible "YYYY-MM-DD"
    open/high/low/close : Precios OHLC
    volume          : Volumen en unidades (volume_units del JSON)

    Indicadores del proveedor (calculados externamente, cargados del JSON)
    -----------------------------------------------------------------------
    rsi             : RSI(14) clásico — valor del proveedor
    macd_line       : Línea MACD
    signal_line     : Línea de señal MACD
    macd_histogram  : Histograma MACD
    ema_20/50/100/200 : EMAs del proveedor (ema_200 usada como filtro estructural)
    bb_mid/upper/lower : Bandas de Bollinger (media, superior, inferior)

    Indicadores calculados por el engine (anti look-ahead)
    -------------------------------------------------------
    rsi_2  : RSI de 2 períodos — señal de reversión a la media (muy sensible)
    atr_14 : Average True Range 14 — para sizing de posición y stops
    adx_14 : Average Directional Index 14 — para detección de régimen
             (no está en el JSON → siempre se calcula desde el buffer FIFO)
    """

    # ── Temporalidad ──────────────────────────────────────────────────────────
    timestamp:      int
    formatted_date: str

    # ── OHLCV ────────────────────────────────────────────────────────────────
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float

    # ── RSI (proveedor) ───────────────────────────────────────────────────────
    rsi: Optional[float] = None          # RSI(14) — del JSON

    # ── MACD (proveedor) ──────────────────────────────────────────────────────
    macd_line:      Optional[float] = None
    signal_line:    Optional[float] = None
    macd_histogram: Optional[float] = None

    # ── EMAs (proveedor) ──────────────────────────────────────────────────────
    ema_20:  Optional[float] = None
    ema_50:  Optional[float] = None
    ema_100: Optional[float] = None
    ema_200: Optional[float] = None      # ← filtro estructural principal (reemplaza SMA200)

    # ── Bollinger Bands (proveedor) ───────────────────────────────────────────
    bb_mid:   Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None

    # ── Indicadores calculados por el engine (inicialmente None) ──────────────
    # REGLA DE ORO: solo se populan desde pronostico_del_clima.compute_and_set_indicators(),
    # después de agregar la vela al buffer FIFO, con datos históricos puros.
    rsi_2:  Optional[float] = None   # RSI(2)  — crítico para reversión a la media
    atr_14: Optional[float] = None   # ATR(14) — volatilidad para sizing y stops
    adx_14: Optional[float] = None   # ADX(14) — fuerza de tendencia para el régimen

    def __repr__(self) -> str:
        rsi2_str   = f"{self.rsi_2:.2f}"   if self.rsi_2   is not None else "N/A"
        ema200_str = f"{self.ema_200:.2f}" if self.ema_200 is not None else "N/A"
        return (
            f"Candle({self.formatted_date} | "
            f"C={self.close:.2f} | "
            f"RSI2={rsi2_str} | "
            f"EMA200={ema200_str})"
        )

    def is_above_ema200(self) -> Optional[bool]:
        """Retorna True si el cierre es mayor a la EMA(200), None si no disponible."""
        if self.ema_200 is None:
            return None
        return self.close > self.ema_200
