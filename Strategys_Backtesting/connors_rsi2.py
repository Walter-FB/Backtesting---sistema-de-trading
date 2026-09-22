"""
connors_rsi2.py — Estrategia RSI(2) de Larry Connors
=====================================================
Primera estrategia del sistema. Diseñada para capturar reversiones
a la media en mercados lateralizados con sesgo alcista estructural.

Filosofía (Larry Connors — "Short Term Trading Strategies That Work"):
  El RSI(2) es un oscilador de ultra corto plazo. Cuando cae por debajo
  de 10 en un activo estructuralmente alcista (precio > EMA200), el activo
  está estadísticamente sobrevendido y tiene alta probabilidad de recuperarse
  hacia la media en los próximos días.

Reglas de la estrategia:
  ENTRADA (señal al cierre, ejecución al OPEN del día siguiente):
    1. bullish_bias = True   → precio de cierre > EMA(200) — filtro estructural
    2. regime = RANGING_MEAN_REVERSION (ADX < 20) — mercado sin tendencia fuerte
       ⚠ DESACTIVADA por defecto: ver la constante USAR_FILTRO_REGIMEN
    3. rsi_2 < 10            → sobreventa extrema de corto plazo
    4. close <= bb_lower     → el precio tocó la Banda de Bollinger inferior
       Es el filtro MÁS selectivo de los cuatro: medido sobre Data_Leo
       rechaza 4.689 de los 5.021 candidatos que ya pasaron el RSI(2) < 10.

  SALIDA (señal al cierre, ejecución al OPEN del día siguiente):
    • Target   : rsi_2 > 50  → reversión a la media completada
    • Time-stop: 10 velas    → evita quedar atrapado si el mercado sigue bajando

REGLA DE ORO: Este módulo jamás accede a datos futuros.
              Solo lee el fifo_buffer en su estado actual (vela actual al final).

Futuras estrategias seguirán la misma interfaz:
  - check_entry(fifo, regime, bullish_bias) -> bool
  - check_exit(fifo, candles_held) -> Optional[str]
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analysis import MarketRegime
from signal_provider import SignalProvider


# ── Parámetros de la estrategia ───────────────────────────────────────────────
RSI2_ENTRY_THRESHOLD: float = 10.0   # RSI(2) debe estar DEBAJO de este valor
RSI2_EXIT_THRESHOLD:  float = 50.0   # RSI(2) debe cruzar ENCIMA de este valor
TIME_STOP_CANDLES:    int   = 10     # Máximo de velas permitidas en posición

# ── Filtro de régimen (condición 2 de la estrategia original) ─────────────────
# Larry Connors plantea esta estrategia para mercados SIN tendencia. Con el
# filtro apagado la estrategia opera en cualquier régimen, y medido sobre
# Data_Leo eso significa que un tercio de las operaciones nacen en
# HIGH_VOLATILITY_CASH — el clima que analysis.py define literalmente como
# "no operar".
#
# Poniéndolo en True la estrategia opera bastante menos y más selectivo.
# Vale la pena probar las dos: el reporte por clima muestra la diferencia.
USAR_FILTRO_REGIMEN: bool = False



# ═══════════════════════════════════════════════════════════════════════════════
# ESTRATEGIA RSI(2) — CONNORS
# ═══════════════════════════════════════════════════════════════════════════════

class RSI2Strategy(SignalProvider):
    """
    Implementación de la estrategia de reversión a la media de Larry Connors.
    Hereda de SignalProvider e implementa el contrato check_entry / check_exit.

    Interfaz pública:
      check_entry(fifo, regime, bullish_bias) -> bool
      check_exit(fifo, candles_held)          -> Optional[str]

    No guarda estado entre llamadas — cada evaluación es independiente.
    Esto la hace predecible y testeable.
    """


    PARAMETROS = {
        "rsi2_entrada": {"default": RSI2_ENTRY_THRESHOLD, "min": 1.0, "max": 40.0, "step": 1.0,
                         "ayuda": "Entra cuando el RSI(2) está por debajo de este valor"},
        "rsi2_salida":  {"default": RSI2_EXIT_THRESHOLD, "min": 20.0, "max": 95.0, "step": 1.0,
                         "ayuda": "Sale cuando el RSI(2) cruza por encima de este valor"},
        "time_stop":    {"default": TIME_STOP_CANDLES, "min": 1, "max": 100, "step": 1,
                         "ayuda": "Máximo de velas en posición"},
        "usar_filtro_regimen": {"default": USAR_FILTRO_REGIMEN,
                         "ayuda": "Solo operar en mercado lateral (RANGING_MEAN_REVERSION)"},
    }

    def check_entry(
        self,
        fifo: deque,
        regime: MarketRegime,
        bullish_bias: Optional[bool],
    ) -> bool:
        """
        Evalúa si se cumplen TODAS las condiciones de entrada.
        La señal se detecta al cierre de la vela; la ejecución ocurre al
        precio de apertura de la vela siguiente (responsabilidad del engine).

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO con la vela actual al final
        regime       : MarketRegime  — régimen detectado por pronostico_del_clima
        bullish_bias : Optional[bool]
                       True  → precio > EMA200 (alcista)
                       False → precio ≤ EMA200 (bajista)
                       None  → EMA200 no disponible aún

        Retorna
        -------
        bool
            True  → señal de entrada confirmada (entrar al open siguiente)
            False → no se cumplen las condiciones

        Condiciones (todas deben cumplirse):
          1. bullish_bias is True  → precio > EMA(200)
          2. regime == RANGING_MEAN_REVERSION
          3. rsi_2 < 10            → sobreventa extrema
          4. close <= bb_lower     → precio en/bajo la BB Inferior (doble confirmación)
        """
        if not fifo:
            return False

        current = fifo[-1]

        # ── Condición 1: Sesgo alcista estructural (precio > EMA200) ─────────
        if bullish_bias is not True:
            return False

        # ── Condición 2: Mercado en rango lateral (ADX < 20) ─────────────────
        # Desactivada por defecto. Estaba comentada en el código original,
        # mientras el docstring seguía anunciándola como obligatoria — se
        # convirtió en un interruptor explícito para que la discrepancia sea
        # visible y se pueda probar con una línea.
        if self.p["usar_filtro_regimen"] and regime != MarketRegime.RANGING_MEAN_REVERSION:
            return False

        # ── Condición 3: RSI(2) en zona de sobreventa extrema (<10) ──────────
        if current.rsi_2 is None or current.rsi_2 >= self.p["rsi2_entrada"]:
            return False

        # ── Condición 4: Precio tocó/cruzó la Banda de Bollinger Inferior ────
        # Doble confirmación de agotamiento: el mercado no solo tiene RSI
        # sobrevendido, sino que el precio ha alcanzado el extremo estadístico
        # de la distribución de volatilidad actual.
        if current.bb_lower is None or current.close > current.bb_lower:
            return False

        # Todas las condiciones se cumplen
        return True

    def check_exit(
        self,
        fifo: deque,
        candles_held: int,
    ) -> Optional[str]:
        """
        Evalúa si se debe cerrar la posición actualmente abierta.
        Verifica el target de RSI(2) y el time-stop.
        La señal se detecta al cierre; la ejecución ocurre al open siguiente.

        Parámetros
        ----------
        fifo         : deque[Candle] — buffer FIFO con la vela actual al final
        candles_held : int — cantidad de velas que lleva abierta la posición
                            (se incrementa en el engine por cada vela procesada)

        Retorna
        -------
        str  → razón de salida:
               "RSI_TARGET"  : RSI(2) cruzó por encima de 50 (target alcanzado)
               "TIME_STOP"   : se completaron las 10 velas máximo
        None → mantener la posición abierta
        """
        # ── Guardia: buffer vacío ─────────────────────────────────────────────
        if not fifo:
            return "TIME_STOP"

        current = fifo[-1]

        # ── Time-stop: máximo de velas superado ──────────────────────────────
        if candles_held >= self.p["time_stop"]:
            return "TIME_STOP"

        # ── Target: RSI(2) cruza por encima de 50 ────────────────────────────
        if current.rsi_2 is not None and current.rsi_2 > self.p["rsi2_salida"]:
            return "RSI_TARGET"

        # Mantener posición
        return None
