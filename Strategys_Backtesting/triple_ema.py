"""
triple_ema.py — Estrategia de Triple EMA (200 / 50 / 12)
==========================================================
Seguimiento de tendencia clásico con tres medias móviles exponenciales
trabajando en capas, cada una con un rol distinto:

    EMA(200)  →  LA ESTACIÓN    ¿el activo está estructuralmente sano?
    EMA(50)   →  LA TENDENCIA   ¿el movimiento intermedio acompaña?
    EMA(12)   →  EL GATILLO     ¿arranca el impulso ahora?

Filosofía
---------
Una sola media da muchas señales falsas: el precio la cruza para arriba y
para abajo constantemente en mercados laterales. Tres medias alineadas son
una condición mucho más exigente — solo se cumple cuando el movimiento tiene
convicción en los tres horizontes a la vez (largo, medio y corto).

El orden "apilado" EMA(12) > EMA(50) > EMA(200) es lo que en el ambiente se
llama tener las medias *alineadas*: el corto plazo va más rápido que el medio,
y el medio más rápido que el largo. Es la firma de una tendencia sana.

Reglas
------
ENTRADA (señal al cierre, ejecución al OPEN de la vela siguiente):
  1. EMA(50) > EMA(200)      → estructura alcista de fondo
  2. close   > EMA(200)      → el precio acompaña esa estructura
  3. DISPARO: EMA(12) cruza por encima de EMA(50) en esta vela

  La condición 3 es un EVENTO, no un estado: se dispara en el momento exacto
  del cruce. Si fuera un estado ("EMA12 por encima de EMA50"), la estrategia
  volvería a entrar en la vela siguiente a cada salida, quedando prácticamente
  siempre comprada.

SALIDA:
  • CRUCE_BAJISTA_12_50 : EMA(12) cruza por debajo de EMA(50) — se apagó el impulso
  • PERDIO_EMA200       : el precio cierra bajo la EMA(200) — se rompió la estructura
  • TIME_STOP           : 60 velas — válvula de seguridad

En qué clima está pensada
--------------------------
Tendencia alcista sostenida (TRENDING_BULLISH). En mercados laterales el
cruce de EMA(12) y EMA(50) se da seguido y en falso, así que esperá ver
peor rendimiento en RANGING_MEAN_REVERSION — el desglose por clima del
reporte te lo va a mostrar.

Nota técnica: de dónde sale cada EMA
-------------------------------------
La EMA(50) y la EMA(200) se leen del Candle (`ema_50`, `ema_200`), donde
vienen calculadas sobre TODA la serie histórica. La EMA(12) no existe en el
Candle, así que se calcula con el toolkit sobre el buffer FIFO.

Esto es intencional y no es intercambiable: el buffer tiene 250 velas, y una
EMA necesita ~3× su período de historia para estabilizarse. Para la EMA(12)
sobran (36 velas), pero una EMA(200) calculada sobre 250 velas estaría mal
converger. Ver GUIA.md § "El toolkit de indicadores".

REGLA DE ORO: este módulo jamás accede a datos futuros. Solo lee el buffer
              FIFO en su estado actual.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from indicators import crossed_above, crossed_below, ema
from signal_provider import SignalProvider


# ── Parámetros de la estrategia ───────────────────────────────────────────────
EMA_GATILLO:     int = 12    # media rápida — se calcula con el toolkit
EMA_TENDENCIA:   int = 50    # media intermedia — viene del Candle (ema_50)
EMA_ESTRUCTURAL: int = 200   # media lenta — viene del Candle (ema_200)
TIME_STOP_VELAS: int = 60    # máximo de velas en posición


class TripleEMAStrategy(SignalProvider):
    """
    Seguimiento de tendencia por alineación de EMA(200), EMA(50) y EMA(12).

    No guarda estado entre llamadas: cada evaluación se resuelve entera
    con lo que hay en el buffer, lo que la hace predecible y testeable.
    """

    # ── ENTRADA ───────────────────────────────────────────────────────────────


    PARAMETROS = {
        "ema_gatillo": {"default": EMA_GATILLO, "min": 3, "max": 50, "step": 1,
                        "ayuda": "Período de la EMA rápida que dispara la entrada"},
        "time_stop":   {"default": TIME_STOP_VELAS, "min": 1, "max": 300, "step": 1,
                        "ayuda": "Máximo de velas en posición"},
    }

    def check_entry(
        self,
        fifo: deque,
        regime: Optional[MarketRegime],
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Entra cuando la EMA(12) cruza por encima de la EMA(50), estando ya
        ambas por encima de la EMA(200).
        """
        if len(fifo) < 2:
            return False

        actual = fifo[-1]
        previa = fifo[-2]

        # ── Guardia: las EMAs del proveedor tienen que estar disponibles ──────
        if None in (actual.ema_50, actual.ema_200, previa.ema_50):
            return False

        # ── Condición 1: estructura alcista (media intermedia sobre la lenta) ─
        if actual.ema_50 <= actual.ema_200:
            return False

        # ── Condición 2: el precio acompaña la estructura ─────────────────────
        if actual.close <= actual.ema_200:
            return False

        # ── Condición 3 (disparo): cruce al alza de la EMA(12) sobre la EMA(50)
        gatillo_hoy = ema(fifo, period=self.p["ema_gatillo"])
        gatillo_ayer = ema(list(fifo)[:-1], period=self.p["ema_gatillo"])

        if gatillo_hoy is None or gatillo_ayer is None:
            return False

        return crossed_above(
            gatillo_ayer, gatillo_hoy,      # serie A: EMA(12) ayer y hoy
            previa.ema_50, actual.ema_50,   # serie B: EMA(50) ayer y hoy
        )

    # ── SALIDA ────────────────────────────────────────────────────────────────

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Sale cuando se apaga el impulso (cruce bajista) o cuando se rompe la
        estructura de fondo (precio bajo la EMA 200).
        """
        if not fifo:
            return "TIME_STOP"

        # ── Válvula de seguridad ──────────────────────────────────────────────
        if candles_held >= self.p["time_stop"]:
            return "TIME_STOP"

        actual = fifo[-1]

        # ── Stop estructural: se perdió la media lenta ────────────────────────
        # Es la salida "dura": si el precio pierde la EMA(200), la premisa
        # entera de la operación dejó de ser válida.
        if actual.ema_200 is not None and actual.close < actual.ema_200:
            return "PERDIO_EMA200"

        if len(fifo) < 2:
            return None

        previa = fifo[-2]
        if None in (actual.ema_50, previa.ema_50):
            return None

        # ── Salida por pérdida de impulso: cruce bajista de la rápida ─────────
        gatillo_hoy = ema(fifo, period=self.p["ema_gatillo"])
        gatillo_ayer = ema(list(fifo)[:-1], period=self.p["ema_gatillo"])

        if gatillo_hoy is None or gatillo_ayer is None:
            return None

        if crossed_below(
            gatillo_ayer, gatillo_hoy,
            previa.ema_50, actual.ema_50,
        ):
            return "CRUCE_BAJISTA_12_50"

        return None
