"""
tp_sl_fijo.py — Take Profit y Stop Loss fijos, en porcentaje
==============================================================
La estrategia que piensa como piensa un trader: "gano X%, pierdo Y%".

Las otras estrategias del sistema salen por CONDICIÓN (cuando un RSI cruza
un nivel, cuando dos medias se cruzan). Esta sale por PRECIO: compra, y
cierra cuando el precio se movió el porcentaje que le dijiste, para arriba
o para abajo. Es la más fácil de razonar y la más fácil de comparar contra
lo que hace cualquier robot comercial.

Para qué sirve, más allá de operar
-----------------------------------
Es el instrumento de medición para dos preguntas que importan mucho:

1. ¿Cuánto cuesta la certeza? Un TP/SL fijo te da resultados acotados y
   predecibles. Las salidas por condición capturan movimientos más grandes
   pero con pérdidas ocasionales de 25-30%. Correr esta contra las otras
   sobre los mismos datos muestra cuánto rendimiento pagás por dormir
   tranquilo.

2. ¿Con qué relación TP/SL hay negocio? Mové las perillas y mirá la
   expectancy. Con comisiones de 0,14% ida y vuelta, un TP de 0,15% está
   muerto antes de nacer; con uno de 2% las comisiones son el 7% del
   movimiento. El dashboard te muestra ese porcentaje directamente.

Reglas
------
ENTRADA (deliberadamente simple: el foco de esta estrategia es la SALIDA):
  1. Opcional: precio por encima de la EMA(200)   (solo_sobre_ema200)
  2. RSI(14) por debajo de `rsi_entrada`           (un retroceso)

SALIDA (evaluada al cierre de cada vela):
  • STOP_LOSS   : el cierre está `stop_loss_pct` por debajo del precio de entrada
  • TAKE_PROFIT : el cierre está `take_profit_pct` por encima
  • TIME_STOP   : pasaron `time_stop` velas

El precio de entrada no se guarda en ningún lado: se lee del buffer. La
entrada se ejecutó al open de la vela que está `candles_held` posiciones
atrás (el motor pone candles_held=1 en la vela de entrada), así que
`list(fifo)[-candles_held].open` es exactamente ese precio.

Dos cosas que hay que saber para leer sus resultados
-----------------------------------------------------
• El stop se evalúa AL CIERRE, no intravela. Si el precio abre con un gap
  del 3% en contra y tu stop era 1%, perdés 3%: el sistema no puede cerrar
  a un precio que no existió al cierre. La pérdida real puede superar al SL.
  En diario pasa poco; en 1 minuto con cripto, pasa.

• Es la única estrategia donde el "R" del reporte se acerca a una unidad
  de riesgo real, porque tiene un stop de verdad. Si además el
  stop_loss_pct coincide con la distancia de 2×ATR que supone el sizing,
  una pérdida es ≈ −1R como el sistema promete.

REGLA DE ORO: este módulo jamás accede a datos futuros. Solo lee el buffer
              FIFO en su estado actual.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from signal_provider import SignalProvider


class TPSLFijoStrategy(SignalProvider):
    """Compra en retrocesos y sale por porcentaje fijo: take profit, stop loss o tiempo."""

    PARAMETROS = {
        "take_profit_pct": {
            "default": 2.0, "min": 0.1, "max": 30.0, "step": 0.1,
            "ayuda": "Cierra con ganancia cuando el precio sube este % desde la entrada",
        },
        "stop_loss_pct": {
            "default": 1.0, "min": 0.1, "max": 30.0, "step": 0.1,
            "ayuda": "Cierra con pérdida cuando el precio baja este % desde la entrada",
        },
        "rsi_entrada": {
            "default": 30.0, "min": 5.0, "max": 60.0, "step": 1.0,
            "ayuda": "Entra cuando el RSI(14) está por debajo de este valor",
        },
        "solo_sobre_ema200": {
            "default": True,
            "ayuda": "Si está activo, solo entra con el precio por encima de la EMA(200)",
        },
        "time_stop": {
            "default": 50, "min": 1, "max": 240, "step": 1,
            "ayuda": "Cierra sin importar el precio después de esta cantidad de velas",
        },
    }

    def check_entry(
        self,
        fifo: deque,
        regime: Optional[MarketRegime],
        bullish_bias: Optional[bool],
    ) -> bool:
        if not fifo:
            return False

        if self.p["solo_sobre_ema200"] and bullish_bias is not True:
            return False

        actual = fifo[-1]
        if actual.rsi is None:
            return False

        return actual.rsi < self.p["rsi_entrada"]

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        if not fifo:
            return "TIME_STOP"

        if candles_held >= self.p["time_stop"]:
            return "TIME_STOP"

        # La vela de entrada ya salió del buffer: no se puede saber el precio
        # de entrada. No debería pasar con time_stop < tamaño del buffer.
        if candles_held > len(fifo):
            return "TIME_STOP"

        precio_entrada = list(fifo)[-max(candles_held, 1)].open
        if precio_entrada <= 0:
            return None

        variacion_pct = (fifo[-1].close - precio_entrada) / precio_entrada * 100.0

        if variacion_pct <= -self.p["stop_loss_pct"]:
            return "STOP_LOSS"
        if variacion_pct >= self.p["take_profit_pct"]:
            return "TAKE_PROFIT"

        return None
