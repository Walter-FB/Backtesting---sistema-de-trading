"""
_plantilla.py — Plantilla para Estrategias Nuevas
==================================================
Copiá este archivo con otro nombre (ej. mi_estrategia.py), completá
check_entry y check_exit, registralo en strategy_factory.py y encendelo.
Los 4 pasos completos están en GUIA.md → "Cómo enchufar una estrategia nueva".

Este archivo NO está registrado en el factory a propósito: es una plantilla,
no una estrategia activa. La lógica de ejemplo que trae abajo funciona y se
puede correr tal cual (RSI sobrevendido + precio sobre la EMA(50)), pero está
para mostrar cómo se usa el toolkit de indicadores, no como estrategia seria.

LO ÚNICO QUE NO PODÉS HACER ACÁ
--------------------------------
Mirar el futuro. Solo tenés acceso a fifo[-1] (la vela actual) y a las
velas anteriores del buffer. Nunca a data[i+1]. El engine se encarga de
que la señal que generes al cierre de hoy se ejecute al open de mañana.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from indicators import (
    adx, atr, bollinger_bands, crossed_above, crossed_below, ema, macd, rsi, sma,
)
from signal_provider import SignalProvider


# ── Parámetros de la estrategia ───────────────────────────────────────────────
# Sacalos siempre a constantes acá arriba: así probás variantes cambiando
# un número, sin tocar la lógica.
RSI_PERIODO:       int   = 14
RSI_SOBREVENTA:    float = 30.0
RSI_SALIDA:        float = 55.0
EMA_TENDENCIA:     int   = 50
TIME_STOP_VELAS:   int   = 20


class PlantillaStrategy(SignalProvider):
    """
    Estrategia de ejemplo: compra cuando el RSI está sobrevendido pero el
    precio sigue por encima de su EMA(50) — es decir, un retroceso dentro
    de una tendencia sana, no una caída libre.
    """

    def check_entry(
        self,
        fifo: deque,
        regime: Optional[MarketRegime],
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Se llama SOLO cuando no hay posición abierta, al cierre de cada vela.
        Devolver True = entrar al open de la vela siguiente.

        Parámetros
        ----------
        fifo         : buffer con la vela actual al final (fifo[-1])
        regime       : clima clásico como Enum, o None si el pronóstico activo
                       no usa el vocabulario clásico (ver GUIA.md → Clima)
        bullish_bias : True si el precio está sobre la EMA(200), False si no,
                       None si todavía no hay dato
        """
        if len(fifo) < EMA_TENDENCIA:
            return False   # todavía no hay historia suficiente

        current = fifo[-1]

        # ── Filtro estructural: solo comprar en contexto alcista ──────────────
        if bullish_bias is not True:
            return False

        # ── Indicadores del toolkit (se calculan desde el buffer, sin futuro) ──
        rsi_actual = rsi(fifo, period=RSI_PERIODO)
        ema_actual = ema(fifo, period=EMA_TENDENCIA)

        if rsi_actual is None or ema_actual is None:
            return False

        # ── Condición 1: RSI sobrevendido ─────────────────────────────────────
        if rsi_actual >= RSI_SOBREVENTA:
            return False

        # ── Condición 2: el precio aguanta sobre su EMA(50) ───────────────────
        if current.close <= ema_actual:
            return False

        return True

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Se llama SOLO cuando hay posición abierta, al cierre de cada vela.
        Devolver un string = salir al open de la vela siguiente, con esa razón.
        Devolver None = mantener la posición.

        El string que devuelvas aparece en los reportes agrupado por razón de
        salida, así que poné nombres que te sirvan para diagnosticar después
        (ej. "RSI_TARGET" y "TIME_STOP" dicen mucho más que "SALIDA_1").
        """
        if not fifo:
            return "TIME_STOP"

        # ── Válvula de seguridad: no quedarse atrapado para siempre ───────────
        if candles_held >= TIME_STOP_VELAS:
            return "TIME_STOP"

        # ── Target: el RSI se recuperó ────────────────────────────────────────
        rsi_actual = rsi(fifo, period=RSI_PERIODO)
        if rsi_actual is not None and rsi_actual > RSI_SALIDA:
            return "RSI_TARGET"

        return None
