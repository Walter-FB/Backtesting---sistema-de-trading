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

    ratio ≈ 1.0   →  la volatilidad reciente es la normal del activo
    ratio < 0.83  →  el activo está MUCHO más quieto que lo habitual

Cómo se eligió el 0.83 (importa, para que nadie lo toque a ciegas)
-------------------------------------------------------------------
NO se eligió por rentabilidad. Se eligió por PERCENTIL: medido sobre las
33.407 velas de Data_Leo, la mediana del ratio es 0.988 y el percentil 10
es 0.828. O sea, 0.83 selecciona aproximadamente el 10% de velas más
quietas — que es exactamente lo que la estrategia dice buscar.

Calibrarlo por percentil y no por resultados evita el autoengaño de
ajustar el umbral hasta que el backtest dé lindo.

Ojo si cambiás el suavizado del ATR: el umbral original era 0.70, elegido
cuando el ATR se calculaba como media simple. Al pasarlo al suavizado de
Wilder (que es mucho más estable) ese 0.70 pasó a seleccionar el 1,15% de
las velas y la estrategia casi dejó de operar. El umbral y el método de
cálculo del ATR van atados.

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
RATIO_COMPRESION:  float = 0.83   # por debajo de esto se considera comprimido
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

        nivel_stop = self._nivel_chandelier(fifo, candles_held)
        if nivel_stop is None:
            return None

        if fifo[-1].close < nivel_stop:
            return "CHANDELIER_STOP"

        return None

    # ── Cálculo del trailing stop ─────────────────────────────────────────────

    @staticmethod
    def _nivel_chandelier(fifo: deque, candles_held: int) -> Optional[float]:
        """
        Nivel del chandelier stop: el MÁS ALTO que alcanzó desde la entrada.

        El trinquete es la parte que importa. Calcular el nivel como
        `máximo − 3×ATR` con el ATR de hoy NO es un trinquete: cuando la
        volatilidad sube, el ATR crece y el nivel se hunde justo en el peor
        momento. Medido sobre datos reales, esa versión bajaba el stop en el
        42% de las velas, con retrocesos de hasta 5,3% en una sola vela.

        Acá se reconstruye el nivel que hubo en CADA vela desde la entrada y
        se devuelve el máximo: así solo puede subir, que es lo que un
        trailing stop promete.

        El ATR se calcula de forma incremental en una sola pasada (el
        suavizado de Wilder es recursivo), así que el costo es el mismo que
        el de una única llamada a `atr()`.

        Retorna None si todavía no hay historia suficiente.
        """
        velas = list(fifo)
        n = len(velas)

        true_ranges = [
            max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            for p, c in zip(velas, velas[1:])
        ]
        if len(true_ranges) < ATR_CORTO:
            return None

        # ATR de Wilder vela por vela. El primer valor corresponde al índice
        # ATR_CORTO de `velas` (necesita ATR_CORTO True Ranges previos).
        atr_val = sum(true_ranges[:ATR_CORTO]) / ATR_CORTO
        atr_por_vela = {ATR_CORTO: atr_val}
        for idx, tr in enumerate(true_ranges[ATR_CORTO:], start=ATR_CORTO + 1):
            atr_val = (atr_val * (ATR_CORTO - 1) + tr) / ATR_CORTO
            atr_por_vela[idx] = atr_val

        # candles_held vale 1 en la vela de entrada (el motor lo incrementa
        # antes de llamar a check_exit), así que -candles_held apunta a ella.
        inicio = max(n - max(candles_held, 1), 0)

        maximo = float("-inf")
        nivel = float("-inf")
        for j in range(inicio, n):
            maximo = max(maximo, velas[j].high)
            atr_j = atr_por_vela.get(j)
            if atr_j is None:
                continue   # vela anterior al calentamiento del ATR
            nivel = max(nivel, maximo - CHANDELIER_ATR * atr_j)

        return None if nivel == float("-inf") else nivel
