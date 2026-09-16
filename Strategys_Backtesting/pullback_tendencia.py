"""
pullback_tendencia.py — Retroceso en Tendencia (con confirmación)
====================================================================
Comprar la corrección dentro de una tendencia sana, pero recién DESPUÉS
de que la corrección haya terminado.

Filosofía
---------
La diferencia con connors_rsi2 es la clave de esta estrategia, y vale la
pena entenderla porque son dos filosofías opuestas sobre el mismo evento:

    connors_rsi2  →  compra MIENTRAS el precio cae (RSI(2) < 10, extremo).
                     Apuesta a que el resorte está tan estirado que rebota.
                     Entra temprano y barato, pero a veces agarra el cuchillo
                     cayendo.

    ESTA          →  espera a que el precio DEJE de caer y dé vuelta.
                     Entra más tarde y más caro, pero solo cuando el mercado
                     ya mostró que la corrección terminó.

Ninguna es mejor en abstracto: son dos formas distintas de pagar por
información. Connors paga con riesgo de seguir cayendo; esta paga con
precio de entrada peor. Correr las dos y comparar es exactamente el tipo
de pregunta que este sistema existe para responder.

Reglas
------
ENTRADA (señal al cierre, ejecución al OPEN de la vela siguiente):
  1. Tendencia intacta : close > EMA(200)  y  EMA(50) > EMA(200)
  2. El retroceso no perforó la EMA(50) : close > EMA(50).
                         Tiene que ser coherente con la salida PERDIO_EMA50:
                         sin esta condición la estrategia abría operaciones
                         que YA cumplían su condición de salida.
  3. Hubo retroceso    : el RSI(14) estuvo bajo 40 en alguna de las
                         últimas 5 velas
  4. CONFIRMACIÓN      : la vela actual cierra por encima del MÁXIMO de la
                         vela anterior

La condición 3 es el corazón de la estrategia. Cerrar por encima del máximo
previo significa que los compradores se impusieron a todo el rango del día
anterior — es la señal más simple y más vieja de que el retroceso terminó.

SALIDA:
  • RSI_OBJETIVO  : RSI(14) > 65 — el rebote maduró, se toma la ganancia
  • PERDIO_EMA50  : el precio cierra bajo la EMA(50) — la premisa se rompió
  • TIME_STOP     : 30 velas — válvula de seguridad

En qué clima está pensada
--------------------------
Tendencia alcista (TRENDING_BULLISH), pero a diferencia de triple_ema no
entra en el arranque del movimiento sino en sus respiros. Debería convivir
bien con tendencias largas y sufrir en mercados bajistas, donde cada
"retroceso" es en realidad el siguiente tramo de caída — para eso está el
filtro de la EMA(200).

Resultado medido (y por qué se deja así)
-----------------------------------------
Sobre los 13 activos de Data_Leo/ en velas diarias, sin optimizar ningún
parámetro, dio 214 operaciones con 29,4% de aciertos y una expectancy de
-0,030R: levemente perdedora.

No se tuneó para darla vuelta. Ajustar los umbrales hasta que el número
cierre sobre este mismo dataset sería sobreajustar, y el backtest dejaría
de significar algo.

La razón estructural del resultado es la parte interesante: la entrada pide
un RSI(14) por debajo de 40 SIN que el precio pierda la EMA(50), y en una
tendencia realmente fuerte eso casi no ocurre — el RSI no llega a bajar
tanto antes de que la tendencia lo levante. El setup termina
auto-seleccionando tendencias débiles y entrecortadas, que son justo las
peores para comprar retrocesos. Una estrategia puede estar perfectamente
implementada y tener una premisa que se sabotea sola.

Puntos por donde atacarla, si querés experimentar: subir RSI_RETROCESO
(retrocesos menos profundos, más frecuentes en tendencias fuertes), bajar
RSI_OBJETIVO (tomar ganancia antes), o cambiar el stop de la EMA(50) por
uno basado en ATR, que le daría aire.

Nota de eficiencia
-------------------
El RSI(14) se lee del campo `rsi` del Candle (viene calculado del proveedor
de datos) en vez de recalcularlo con el toolkit sobre cinco ventanas. Es el
mismo número y ahorra ~70 operaciones por vela, que importa cuando se corren
millones de velas de 1 minuto.

REGLA DE ORO: este módulo jamás accede a datos futuros. Solo lee el buffer
              FIFO en su estado actual.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from signal_provider import SignalProvider


# ── Parámetros de la estrategia ───────────────────────────────────────────────
RSI_RETROCESO:      float = 40.0   # por debajo de esto se considera retroceso
RSI_OBJETIVO:       float = 65.0   # por encima de esto se toma la ganancia
VENTANA_RETROCESO:  int   = 5      # cuántas velas atrás buscar el retroceso
TIME_STOP_VELAS:    int   = 30     # máximo de velas en posición


class PullbackTendenciaStrategy(SignalProvider):
    """
    Compra retrocesos dentro de una tendencia alcista, esperando la vela
    de confirmación antes de entrar.
    """

    # ── ENTRADA ───────────────────────────────────────────────────────────────

    def check_entry(
        self,
        fifo: deque,
        regime: Optional[MarketRegime],
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Entra tras un retroceso, en la primera vela que confirma el giro.
        """
        if len(fifo) < VENTANA_RETROCESO + 1:
            return False

        actual = fifo[-1]
        previa = fifo[-2]

        # ── Guardia: las EMAs del proveedor tienen que estar disponibles ──────
        if None in (actual.ema_50, actual.ema_200):
            return False

        # ── Condición 1: la tendencia de fondo sigue intacta ──────────────────
        if actual.close <= actual.ema_200:
            return False
        if actual.ema_50 <= actual.ema_200:
            return False

        # ── Condición 1b: el retroceso no perforó la EMA(50) ──────────────────
        # Esta condición tiene que ser coherente con la salida PERDIO_EMA50:
        # sin ella, la estrategia entra en operaciones que YA cumplen la
        # condición de salida y las cierra en la vela siguiente.
        # Un retroceso que perdió la EMA(50) es más profundo que un respiro
        # dentro de la tendencia — que es lo único que esta estrategia compra.
        if actual.close <= actual.ema_50:
            return False

        # ── Condición 2: hubo un retroceso reciente ───────────────────────────
        recientes = list(fifo)[-VENTANA_RETROCESO:]
        hubo_retroceso = any(
            c.rsi is not None and c.rsi < RSI_RETROCESO for c in recientes
        )
        if not hubo_retroceso:
            return False

        # ── Condición 3: confirmación — se supera el máximo de la vela previa ─
        return actual.close > previa.high

    # ── SALIDA ────────────────────────────────────────────────────────────────

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Sale al madurar el rebote, o si el precio pierde la EMA(50).
        """
        if not fifo:
            return "TIME_STOP"

        # ── Válvula de seguridad ──────────────────────────────────────────────
        if candles_held >= TIME_STOP_VELAS:
            return "TIME_STOP"

        actual = fifo[-1]

        # ── Stop: se rompió la estructura que justificaba la operación ────────
        if actual.ema_50 is not None and actual.close < actual.ema_50:
            return "PERDIO_EMA50"

        # ── Target: el rebote maduró ──────────────────────────────────────────
        if actual.rsi is not None and actual.rsi > RSI_OBJETIVO:
            return "RSI_OBJETIVO"

        return None
