"""
test_multi_timeframe.py — Tests de alineación entre timeframes
================================================================
Verifica lo único que realmente importa del clima multi-timeframe: que
parado en una vela de 1m NUNCA se use una vela diaria que todavía no cerró.

Si este test falla, los backtests multi-timeframe mienten (dan mejores
resultados de los reales, porque el sistema estaría viendo el futuro).

Se corre sin pytest:
    python tests/test_multi_timeframe.py
"""

from __future__ import annotations

import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from climate_provider import ClimateProvider, ClimateReading
from Climas_Backtesting.multi_timeframe import MultiTimeframeClimate, timeframe_to_seconds
from models import Candle

DIA = 86_400
MINUTO = 60


def _vela(ts: int, close: float = 100.0) -> Candle:
    """Vela mínima para tests — el precio no importa acá, sí el timestamp."""
    return Candle(
        timestamp=ts,
        formatted_date=f"ts={ts}",
        open=close, high=close * 1.01, low=close * 0.99, close=close,
        volume=1000.0,
    )


class _ClimaEspia(ClimateProvider):
    """
    Pronóstico de mentira que no clasifica nada: solo reporta cuántas velas
    HTF vio y cuál fue la última. Sirve para auditar la alineación sin que
    la lógica del clima clásico (ADX, EMA200) meta ruido en el test.
    """

    def detect(self, fifo: deque) -> ClimateReading:
        ultima = fifo[-1]
        return ClimateReading(
            label="ESPIA",
            details={"velas_vistas": len(fifo), "ultimo_ts": ultima.timestamp},
        )


def test_nunca_usa_la_vela_htf_en_curso() -> None:
    """
    Parado en cualquier minuto del día N, la última vela diaria usable es
    la del día N-1 (la del día N todavía se está formando).
    """
    dias = [_vela(d * DIA) for d in range(10)]
    clima = MultiTimeframeClimate(dias, htf_timeframe="1d", inner=_ClimaEspia())

    for dia_actual in range(1, 10):
        for minuto in (0, 1, 60, 600, 1439):   # varios momentos dentro del día
            ts = dia_actual * DIA + minuto * MINUTO
            lectura = clima.detect(deque([_vela(ts)]))

            esperado_ts = (dia_actual - 1) * DIA
            assert lectura.details["ultimo_ts"] == esperado_ts, (
                f"En el día {dia_actual} minuto {minuto} se usó la vela diaria "
                f"ts={lectura.details['ultimo_ts']}, se esperaba ts={esperado_ts}"
            )

    print("✓ nunca usa la vela HTF en curso")


def test_el_cierre_habilita_la_vela_exactamente_en_su_borde() -> None:
    """
    La vela diaria del día 0 (00:00 a 23:59:59) recién puede usarse a partir
    del instante exacto en que cierra: ts = 1 * DIA. Ni un segundo antes.
    """
    dias = [_vela(d * DIA) for d in range(3)]
    clima = MultiTimeframeClimate(dias, htf_timeframe="1d", inner=_ClimaEspia())

    # Un segundo ANTES del cierre del día 0 → todavía no hay ninguna vela usable
    lectura = clima.detect(deque([_vela(DIA - 1)]))
    assert lectura.label == "WAITING_FOR_DATA", (
        f"Antes del primer cierre no debería haber clima, se obtuvo '{lectura.label}'"
    )

    # Exactamente en el cierre del día 0 → ya se puede usar la vela del día 0
    lectura = clima.detect(deque([_vela(DIA)]))
    assert lectura.details["ultimo_ts"] == 0, "En el borde de cierre debe entrar la vela del día 0"

    print("✓ el cierre habilita la vela exactamente en su borde")


def test_cada_vela_htf_se_procesa_una_sola_vez() -> None:
    """
    Aunque se consulte el clima miles de veces (una por vela de 1m), cada
    vela diaria tiene que entrar al buffer una sola vez y en orden — si se
    procesara de nuevo, el estado interno del pronóstico (ej. la pendiente
    del ADX) quedaría corrupto.
    """
    dias = [_vela(d * DIA) for d in range(5)]
    clima = MultiTimeframeClimate(dias, htf_timeframe="1d", inner=_ClimaEspia())

    # Minutos de los días 0, 1 y 2, consultando el clima en cada uno
    for minuto in range(3 * 1440):
        lectura = clima.detect(deque([_vela(minuto * MINUTO)]))

    # En el ÚLTIMO minuto del día 2 solo cerraron los días 0 y 1: el día 2
    # cierra recién un minuto después. Son 2 velas, no 3.
    assert lectura.details["velas_vistas"] == 2, (
        f"Se esperaban 2 velas diarias en el buffer, hay {lectura.details['velas_vistas']}"
    )

    # Un minuto más (ya en el día 3) → ahora sí cerró el día 2
    lectura = clima.detect(deque([_vela(3 * 1440 * MINUTO)]))
    assert lectura.details["velas_vistas"] == 3
    assert lectura.details["ultimo_ts"] == 2 * DIA

    print("✓ cada vela HTF se procesa una sola vez")


def test_salto_temporal_no_saltea_velas() -> None:
    """
    Si el stream de 1m tiene un hueco (datos faltantes, mercado caído), al
    volver hay que ponerse al día con TODAS las velas diarias que cerraron
    en el medio, no solo con la última.
    """
    dias = [_vela(d * DIA) for d in range(10)]
    clima = MultiTimeframeClimate(dias, htf_timeframe="1d", inner=_ClimaEspia())

    clima.detect(deque([_vela(DIA)]))                    # día 1: cerró el día 0
    lectura = clima.detect(deque([_vela(6 * DIA)]))      # salto directo al día 6

    assert lectura.details["velas_vistas"] == 6, (
        f"Tras el salto deberían haberse procesado 6 velas diarias (días 0–5), "
        f"hay {lectura.details['velas_vistas']}"
    )
    assert lectura.details["ultimo_ts"] == 5 * DIA

    print("✓ un salto temporal se pone al día sin saltear velas")


def test_conversion_de_timeframes() -> None:
    assert timeframe_to_seconds("1m") == 60
    assert timeframe_to_seconds("15m") == 900
    assert timeframe_to_seconds("4h") == 14_400
    assert timeframe_to_seconds("12h") == 43_200
    assert timeframe_to_seconds("1d") == 86_400

    for invalido in ("1x", "hola", "", "d1"):
        try:
            timeframe_to_seconds(invalido)
        except ValueError:
            pass
        else:
            raise AssertionError(f"'{invalido}' debería haber sido rechazado")

    print("✓ conversión de timeframes")


def main() -> None:
    print("\n── Tests de clima multi-timeframe " + "─" * 36)
    test_conversion_de_timeframes()
    test_nunca_usa_la_vela_htf_en_curso()
    test_el_cierre_habilita_la_vela_exactamente_en_su_borde()
    test_cada_vela_htf_se_procesa_una_sola_vez()
    test_salto_temporal_no_saltea_velas()
    print("── Todos los tests pasaron " + "─" * 43 + "\n")


if __name__ == "__main__":
    main()
