"""
momentum_breakout.py — Estrategia de Ruptura de Momentum (Seguimiento de Tendencia)
====================================================================================
Diseñada para capturar movimientos largos (semanas / meses) en régimen tendencial.
Opera únicamente cuando el ADX confirma tendencia alcista (TRENDING_BULLISH).

Filosofía:
  Cuando el mercado tiene tendencia confirmada (ADX > 25 subiendo) y el precio
  rompe el máximo de los últimos 20 días, es señal de que la fuerza compradora
  es real y tiene momentum. Se entra en la dirección del movimiento y se deja
  correr hasta que el precio pierda fuerza (trailing stop de 10 días).

Reglas de la estrategia:
  ENTRADA (señal al cierre, ejecución al OPEN del día siguiente):
    1. regime == TRENDING_BULLISH      → ADX > 25 y pendiente positiva
    2. Higher High (60 días)           → close actual > max high de los últimos 60 días
    3. Donchian Breakout (20 días)     → close actual > max high de los últimos 20 días
       (el Higher High de 60 ya implica esto — se verifica igual para claridad)

  SALIDA:
    • Trailing Stop (10 días) : close < min low de los últimos 10 días
    • Time-stop  (60 velas)   : válvula de seguridad si el mercado se para

Sizing: igual que RSI2 — 1% del capital / (ATR × 2.0)
  Como el stop es más amplio que en RSI2, se compran menos acciones → mismo
  riesgo en dólares pero menor exposición porcentual.

REGLA DE ORO: jamás accede a datos futuros. Solo lee fifo[-1] y velas anteriores
              dentro del buffer FIFO (anti look-ahead bias).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from signal_provider import SignalProvider
from .connors_rsi2 import RiskManager  # import relativo dentro del paquete


# ── Parámetros de la estrategia ───────────────────────────────────────────────
DONCHIAN_BREAKOUT_PERIOD: int   = 20    # días para el canal de Donchian (trigger entrada)
HIGHER_HIGH_PERIOD:       int   = 60    # días para el filtro estructural de máximos
TRAILING_STOP_PERIOD:     int   = 20    # días para el trailing stop de mínimos (ampliado de 10)
TIME_STOP_CANDLES:        int   = 60    # válvula de seguridad: máximo de velas en posición

# Sizing idéntico al RSI2 — reutiliza los mismos parámetros de riesgo
MOMENTUM_RISK_PCT:       float = 0.01  # 1% del capital por trade
MOMENTUM_ATR_MULTIPLIER: float = 2.0   # stop = 2 × ATR bajo el precio de entrada


# ═══════════════════════════════════════════════════════════════════════════════
# ESTRATEGIA MOMENTUM BREAKOUT
# ═══════════════════════════════════════════════════════════════════════════════

class MomentumBreakoutStrategy(SignalProvider):
    """
    Estrategia de ruptura de momentum con seguimiento de tendencia.
    Hereda de SignalProvider e implementa el contrato check_entry / check_exit.

    Interfaz pública:
      check_entry(fifo, regime, bullish_bias) -> bool
      check_exit(fifo, candles_held)          -> Optional[str]

    No guarda estado entre llamadas salvo el trailing stop mínimo interno,
    que se recalcula en cada vela desde el FIFO.
    """

    def check_entry(
        self,
        fifo: deque,
        regime: MarketRegime,
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Evalúa si se cumplen TODAS las condiciones de entrada Momentum.
        La señal se detecta al cierre; la ejecución ocurre al open siguiente.

        Condiciones (todas deben cumplirse):
          1. regime == TRENDING_BULLISH   → tendencia confirmada con ADX subiendo
          2. Higher High (60 días)        → close > max(highs[-61:-1])
          3. Donchian Breakout (20 días)  → close > max(highs[-21:-1])
        """
        if not fifo:
            return False

        # ── Condición 1: Régimen tendencial alcista (ADX > 25 subiendo) ───────
        if regime != MarketRegime.TRENDING_BULLISH:
            return False

        # ── Guardia: necesitamos al menos 61 velas para los cálculos ──────────
        # 60 para el Higher High + 1 para la vela actual
        if len(fifo) < HIGHER_HIGH_PERIOD + 1:
            return False

        current = fifo[-1]

        # Convertir el deque a lista para slicing (más claro)
        fifo_list = list(fifo)

        # ── Condición 2: Higher High de 60 días ───────────────────────────────
        # El cierre actual supera el máximo de los últimos 60 días (sin incluir hoy)
        highs_last_60 = [c.high for c in fifo_list[-(HIGHER_HIGH_PERIOD + 1):-1]]
        if not highs_last_60:
            return False
        max_high_60_days = max(highs_last_60)

        if current.close <= max_high_60_days:
            return False

        # ── Condición 3: Donchian Breakout de 20 días ─────────────────────────
        # El cierre actual supera el máximo de los últimos 20 días (sin incluir hoy)
        # Nota: ya implícito en Higher High 60, pero se verifica para legibilidad
        highs_last_20 = [c.high for c in fifo_list[-(DONCHIAN_BREAKOUT_PERIOD + 1):-1]]
        if not highs_last_20:
            return False
        donchian_upper = max(highs_last_20)

        if current.close <= donchian_upper:
            return False

        # Todas las condiciones se cumplen — señal de entrada confirmada
        return True

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Evalúa si se debe cerrar la posición abierta.

        Retorna
        -------
        "DONCHIAN_TRAILING_STOP" : close < min low de los últimos 10 días
        "TIME_STOP"              : válvula de seguridad — 60 velas máximas
        None                     : mantener posición
        """
        if not fifo:
            return "TIME_STOP"

        # ── Time-stop: válvula de seguridad ───────────────────────────────────
        if candles_held >= TIME_STOP_CANDLES:
            return "TIME_STOP"

        # ── Trailing Stop: close < mínimo de los últimos 10 días ─────────────
        if len(fifo) < TRAILING_STOP_PERIOD + 1:
            return None  # no hay suficiente historia — mantener

        fifo_list = list(fifo)
        current = fifo[-1]

        # Mínimo de los últimos 10 días (sin incluir la vela actual)
        lows_last_10 = [c.low for c in fifo_list[-(TRAILING_STOP_PERIOD + 1):-1]]
        trailing_stop_level = min(lows_last_10)

        if current.close < trailing_stop_level:
            return "DONCHIAN_TRAILING_STOP"

        return None
