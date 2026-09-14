"""
compresion_volatilidad.py — Ruptura por Compresión de Volatilidad
===================================================================
No opera dirección: opera el CAMBIO DE RÉGIMEN de volatilidad.

Filosofía
---------
La volatilidad de un mercado no es constante: se contrae y se expande en
ciclos. Cuando un activo se aquieta — el rango de las velas se achica, nadie
toma decisiones, el gráfico se aplana — está acumulando energía. Tarde o
temprano esa compresión se resuelve con un movimiento amplio. La estrategia
no intenta adivinar para qué lado: espera la compresión y compra la ruptura.

Esta es una familia distinta a la de las otras estrategias del sistema:
  • connors_rsi2      → reversión a la media (compra caídas)
  • triple_ema        → seguimiento de tendencia (compra tendencias)
  • ESTA              → régimen de volatilidad (compra explosiones)

Cómo se mide la compresión
---------------------------
Comparando dos ATR de distinto plazo:

    ratio = ATR(10) / ATR(50)

    ratio ≈ 1.0  →  la volatilidad reciente es la normal del activo
    ratio < 0.7  →  el activo está MUCHO más quieto que lo habitual (compresión)

Se mide sobre el buffer SIN incluir la vela actual: lo que interesa es que
veníamos comprimidos y que HOY rompe. Si se incluyera la vela de ruptura
—que por definición es grande— el ATR corto se dispararía y taparía
justamente la señal que se está buscando.

Reglas
------
ENTRADA (señal al cierre, ejecución al OPEN de la vela siguiente):
  1. Compresión : ATR(10) / ATR(50) < 0.70 en la vela previa
  2. Ruptura    : el cierre actual supera el máximo de las últimas 20 velas

SALIDA:
  • CHANDELIER_STOP : el precio cae más de 3×ATR desde el máximo alcanzado
                      desde la entrada (trailing stop que sigue al máximo)
  • TIME_STOP       : 100 velas — válvula de seguridad

Sobre el Chandelier Stop
-------------------------
Es un trailing stop que cuelga del techo (de ahí el nombre: "candelabro").
Se ancla al máximo alcanzado desde que se entró y se mantiene 3 ATR por
debajo. Sube cuando el precio sube, pero nunca baja. Deja correr las
ganancias mientras la tendencia aguante, y corta cuando se rompe.

Se calcula sin guardar estado: `candles_held` dice cuántas velas pasaron
desde la entrada, y el máximo se busca en esa ventana del buffer.

Limitación conocida: si la posición dura más que el buffer (250 velas), el
máximo se busca sobre las últimas 250 y no sobre la operación entera. Con
el time-stop en 100 velas no se llega a ese caso.

En qué clima está pensada
--------------------------
Agnóstica de clima a propósito — es la contracara del resto. La compresión
suele darse en mercados laterales (RANGING_MEAN_REVERSION) y la ruptura
inaugura la tendencia, así que sus operaciones nacen en un clima y mueren
en otro. Es interesante justamente por eso: el desglose por clima del
reporte la va a mostrar muy distinta a las demás.

REGLA DE ORO: este módulo jamás accede a datos futuros. Solo lee el buffer
              FIFO en su estado actual.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from indicators import atr
from signal_provider import SignalProvider


# ── Parámetros de la estrategia ───────────────────────────────────────────────
ATR_CORTO:         int   = 10     # volatilidad reciente
ATR_LARGO:         int   = 50     # volatilidad "normal" del activo
RATIO_COMPRESION:  float = 0.70   # por debajo de esto se considera comprimido
RUPTURA_VELAS:     int   = 20     # ventana del máximo a romper
CHANDELIER_ATR:    float = 3.0    # distancia del trailing stop, en ATR
TIME_STOP_VELAS:   int   = 100    # máximo de velas en posición


class CompresionVolatilidadStrategy(SignalProvider):
    """
    Compra la ruptura de un rango que venía comprimido en volatilidad,
    y la acompaña con un trailing stop tipo chandelier.
    """

    # ── ENTRADA ───────────────────────────────────────────────────────────────

    def check_entry(
        self,
        fifo: deque,
        regime: Optional[MarketRegime],
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Entra cuando un activo comprimido rompe al alza el máximo reciente.
        """
        # Necesitamos historia para el ATR largo, más la vela previa
        if len(fifo) < ATR_LARGO + 2:
            return False

        actual = fifo[-1]
        previas = list(fifo)[:-1]   # el buffer SIN la vela de ruptura

        # ── Condición 1: veníamos comprimidos ─────────────────────────────────
        atr_corto = atr(previas, period=ATR_CORTO)
        atr_largo = atr(previas, period=ATR_LARGO)

        if atr_corto is None or atr_largo is None or atr_largo <= 0:
            return False

        if (atr_corto / atr_largo) >= RATIO_COMPRESION:
            return False

        # ── Condición 2: hoy rompe el máximo de las últimas N velas ───────────
        # Se excluye la vela actual del cálculo del máximo: si se incluyera,
        # su propio high formaría parte del techo a superar.
        maximos = [c.high for c in list(fifo)[-(RUPTURA_VELAS + 1):-1]]
        if not maximos:
            return False

        return actual.close > max(maximos)

    # ── SALIDA ────────────────────────────────────────────────────────────────

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Sale por trailing stop tipo chandelier: 3 ATR por debajo del máximo
        alcanzado desde la entrada.
        """
        if not fifo:
            return "TIME_STOP"

        # ── Válvula de seguridad ──────────────────────────────────────────────
        if candles_held >= TIME_STOP_VELAS:
            return "TIME_STOP"

        actual = fifo[-1]

        atr_actual = atr(fifo, period=ATR_CORTO)
        if atr_actual is None:
            return None

        # ── Máximo alcanzado desde la entrada ─────────────────────────────────
        # candles_held=0 significa que todavía no pasó ninguna vela completa
        # en posición; el max(..., 1) evita que list[-0:] devuelva el buffer
        # entero, que daría un máximo histórico en vez del de la operación.
        velas_en_posicion = list(fifo)[-max(candles_held, 1):]
        maximo_alcanzado = max(c.high for c in velas_en_posicion)

        nivel_stop = maximo_alcanzado - (CHANDELIER_ATR * atr_actual)

        if actual.close < nivel_stop:
            return "CHANDELIER_STOP"

        return None
