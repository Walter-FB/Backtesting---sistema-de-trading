"""
test_indicadores.py — Tests de la matemática de los indicadores
=================================================================
Cada test de acá corresponde a un bug real que ya ocurrió. No son tests
hipotéticos: son la red para que esos errores no vuelvan.

Los tres que aparecieron en la auditoría:
  1. El ADX devolvía el DX (le faltaba el suavizado final). Distorsionaba
     toda la clasificación de clima, porque el RegimeDetector compara ese
     número contra umbrales de 20/25/40.
  2. El RSI usaba media simple en vez del suavizado de Wilder — o sea, era
     el RSI de Cutler, otro indicador. Difería 10 puntos del campo `.rsi`
     que traen las velas.
  3. El ATR, lo mismo. Y el ATR dimensiona TODAS las posiciones.

Se corre sin pytest:
    python tests/test_indicadores.py
"""

from __future__ import annotations

import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import JSONDataLoader
import indicators as ind

RUTA_DATOS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Data_Leo", "NASDAQ_COST", "COST_1D_3000Bars.json",
)
TOLERANCIA = 1e-9


# ── Implementaciones de referencia, escritas desde la definición ──────────────

def _rsi_wilder(closes, period=14):
    ganancias = perdidas = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        ganancias += max(d, 0.0)
        perdidas += max(-d, 0.0)
    prom_g, prom_p = ganancias / period, perdidas / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        prom_g = (prom_g * (period - 1) + max(d, 0.0)) / period
        prom_p = (prom_p * (period - 1) + max(-d, 0.0)) / period
    return 100.0 if prom_p == 0 else 100 - 100 / (1 + prom_g / prom_p)


def _atr_wilder(highs, lows, closes, period=14):
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    valor = sum(trs[:period]) / period
    for tr in trs[period:]:
        valor = (valor * (period - 1) + tr) / period
    return valor


def _adx_wilder(highs, lows, closes, period=14):
    trs, pdm, mdm = [], [], []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        sube = highs[i] - highs[i - 1]
        baja = lows[i - 1] - lows[i]
        pdm.append(sube if (sube > baja and sube > 0) else 0.0)
        mdm.append(baja if (baja > sube and baja > 0) else 0.0)

    def suavizar(serie):
        out = [sum(serie[:period])]
        for v in serie[period:]:
            out.append(out[-1] - out[-1] / period + v)
        return out

    s_tr, s_pdm, s_mdm = suavizar(trs), suavizar(pdm), suavizar(mdm)
    dx = []
    for tr, pd_, md in zip(s_tr, s_pdm, s_mdm):
        if tr == 0:
            dx.append(0.0)
            continue
        pdi, mdi = 100 * pd_ / tr, 100 * md / tr
        total = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / total if total else 0.0)
    # El paso que faltaba: suavizado de Wilder del DX
    valor = sum(dx[:period]) / period
    for v in dx[period:]:
        valor = (valor * (period - 1) + v) / period
    return valor


def _buffer():
    velas = JSONDataLoader().load_from_json(RUTA_DATOS)[-400:]
    return deque(velas, maxlen=250)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_rsi_es_wilder() -> None:
    buf = _buffer()
    closes = [c.close for c in buf]
    esperado = _rsi_wilder(closes, 14)
    obtenido = ind.rsi(buf, 14)
    assert abs(obtenido - esperado) < TOLERANCIA, (
        f"RSI: se obtuvo {obtenido:.6f}, se esperaba {esperado:.6f}. "
        f"Si la diferencia ronda los 10 puntos, volvió a ser el RSI de Cutler."
    )
    print("✓ el RSI usa el suavizado de Wilder")


def test_rsi_coincide_con_el_campo_del_candle() -> None:
    """
    El toolkit y el campo `.rsi` de la vela tienen que dar el MISMO número.
    Si divergen, una estrategia que use `indicators.rsi()` y otra que lea
    `candle.rsi` están mirando indicadores distintos sin saberlo.
    """
    buf = _buffer()
    del_campo = buf[-1].rsi
    del_toolkit = ind.rsi(buf, 14)
    assert del_campo is not None
    assert abs(del_toolkit - del_campo) < 0.01, (
        f"toolkit={del_toolkit:.4f} vs campo .rsi={del_campo:.4f}"
    )
    print("✓ el RSI del toolkit coincide con el campo .rsi de la vela")


def test_atr_es_wilder() -> None:
    buf = _buffer()
    esperado = _atr_wilder([c.high for c in buf], [c.low for c in buf], [c.close for c in buf], 14)
    obtenido = ind.atr(buf, 14)
    assert abs(obtenido - esperado) < TOLERANCIA, (
        f"ATR: se obtuvo {obtenido:.6f}, se esperaba {esperado:.6f}"
    )
    print("✓ el ATR usa el suavizado de Wilder")


def test_adx_es_adx_y_no_dx() -> None:
    """
    El bug original: se calculaba el DX y se devolvía sin promediarlo sobre
    el período — que es justamente el paso que lo convierte en ADX.
    """
    buf = _buffer()
    esperado = _adx_wilder([c.high for c in buf], [c.low for c in buf], [c.close for c in buf], 14)
    obtenido = ind.adx(buf, 14)
    assert abs(obtenido - esperado) < TOLERANCIA, (
        f"ADX: se obtuvo {obtenido:.6f}, se esperaba {esperado:.6f}. "
        f"Si da bastante más alto y errático, probablemente volvió a devolver el DX."
    )
    print("✓ el ADX es ADX (con el suavizado final), no DX")


def test_una_sola_implementacion() -> None:
    """
    pronostico_del_clima.py no debe volver a tener su propia copia de los
    indicadores: tiene que delegar en indicators.py. Tres implementaciones
    paralelas que se desincronizan fue el origen de todo este lío.
    """
    import pronostico_del_clima as pdc

    for nombre in ("_calc_rsi", "_calc_atr", "_calc_adx"):
        assert not hasattr(pdc, nombre), (
            f"pronostico_del_clima volvió a implementar {nombre} por su cuenta. "
            f"Tiene que usar indicators.py, que es la única implementación."
        )

    # Y el valor que escribe en la vela tiene que ser el del toolkit
    buf = _buffer()
    pdc.compute_and_set_indicators(buf)
    assert abs(buf[-1].adx_14 - ind.adx(buf, pdc.ADX_PERIOD)) < TOLERANCIA
    assert abs(buf[-1].atr_14 - ind.atr(buf, pdc.ATR_PERIOD)) < TOLERANCIA
    print("✓ hay una sola implementación de cada indicador")


def test_casos_borde() -> None:
    vacio: deque = deque()
    for fn in (ind.rsi, ind.atr, ind.adx):
        assert fn(vacio) is None, f"{fn.__name__} debería devolver None con buffer vacío"

    buf = _buffer()
    corto = deque(list(buf)[:3], maxlen=250)
    assert ind.rsi(corto, 14) is None
    assert ind.atr(corto, 14) is None
    assert ind.adx(corto, 14) is None

    # Precios constantes: sin pérdidas → RSI 100, sin rango → ATR 0
    from models import Candle
    planas = deque(
        [Candle(timestamp=i, formatted_date=str(i), open=10.0, high=10.0,
                low=10.0, close=10.0, volume=1.0) for i in range(60)],
        maxlen=250,
    )
    assert ind.rsi(planas, 14) == 100.0
    assert ind.atr(planas, 14) == 0.0
    assert ind.adx(planas, 14) == 0.0
    print("✓ casos borde (buffer vacío, corto, precios constantes)")


def main() -> None:
    print("\n── Tests de indicadores " + "─" * 46)
    test_rsi_es_wilder()
    test_rsi_coincide_con_el_campo_del_candle()
    test_atr_es_wilder()
    test_adx_es_adx_y_no_dx()
    test_una_sola_implementacion()
    test_casos_borde()
    print("── Todos los tests pasaron " + "─" * 43 + "\n")


if __name__ == "__main__":
    main()
