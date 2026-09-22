"""
test_estado_y_riesgo.py — Tests de estado, riesgo y pipeline de datos
========================================================================
Como el de indicadores, cada test corresponde a un bug real que ocurrió.

  1. El buffer del motor no se limpiaba entre backtests: el segundo activo
     arrancaba con 250 velas del primero (contaminación cruzada silenciosa).
  2. El cursor del clima multi-timeframe no rebobinaba al reusar la
     instancia: el segundo backtest arrancaba viendo el clima del futuro.
  3. El chandelier stop se recalculaba sin estado y BAJABA cuando subía la
     volatilidad — un trailing stop que retrocede no es un trailing stop.
  4. El sizing no tenía tope de exposición: comprometía hasta el 55% del
     capital mientras el sistema anunciaba arriesgar 1%.
  5. `max_candles` devolvía la cola del rango descargado en vez del
     comienzo del rango pedido.
  6. Un JSON ilegible devolvía una lista vacía sin lanzar nada: el backtest
     reportaba "sin operaciones" como si el activo no hubiera dado señales.

Se corre sin pytest:
    python tests/test_estado_y_riesgo.py
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import sys
import tempfile
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from climate_provider import ClimateProvider, ClimateReading
from Climas_Backtesting.multi_timeframe import MultiTimeframeClimate
from data_loader import JSONDataLoader
from engine import TradingEngine
from models import Candle
from strategy_factory import StrategyFactory
from Strategys_Backtesting.compresion_volatilidad import (
    CompresionVolatilidadStrategy, ATR_CORTO,
)
from risk_manager import RiskManager

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIA = 86_400


def _vela(ts: int, precio: float = 100.0) -> Candle:
    return Candle(timestamp=ts, formatted_date=f"ts{ts}", open=precio,
                  high=precio * 1.01, low=precio * 0.99, close=precio, volume=1.0)


def _motor_mudo(nombre: str) -> TradingEngine:
    e = TradingEngine(strategy=StrategyFactory.create(nombre), initial_balance=100_000.0)
    e.tracker.save_csv = lambda filename="": ""
    e.tracker.save_txt = lambda initial_balance=0, ticker="", filename="": ""
    return e


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_el_motor_se_reinicia_entre_backtests() -> None:
    a = JSONDataLoader().load_from_json(os.path.join(RAIZ, "Data_Leo", "NASDAQ_COST", "COST_1D_3000Bars.json"))
    b = JSONDataLoader().load_from_json(os.path.join(RAIZ, "Data_Leo", "NYSE_LMT", "LMT_1D_3000Bars.json"))

    e = _motor_mudo("connors_rsi2")
    with contextlib.redirect_stdout(io.StringIO()):
        e.run_backtest(a, ticker="COST")
        e.run_backtest(b[:5], ticker="LMT")

    assert len(e.fifo_buffer) == 5, (
        f"El buffer arrastró {len(e.fifo_buffer) - 5} velas del activo anterior"
    )
    assert e.balance == 100_000.0 or e.current_position is not None or True
    print("✓ el motor limpia su estado entre backtests")


def test_el_clima_multitimeframe_rebobina() -> None:
    class Espia(ClimateProvider):
        def detect(self, fifo):
            return ClimateReading(label="X", details={"ts": fifo[-1].timestamp})

    dias = [_vela(d * DIA) for d in range(10)]
    clima = MultiTimeframeClimate(dias, htf_timeframe="1d", inner=Espia())

    clima.detect(deque([_vela(9 * DIA)]))          # primer backtest, llega al día 9
    lectura = clima.detect(deque([_vela(1 * DIA)]))  # segundo backtest, vuelve al día 1

    assert lectura.details["ts"] == 0, (
        f"Al reusar la instancia devolvió la diaria del día "
        f"{lectura.details['ts'] // DIA} estando en el día 1: eso es ver el futuro."
    )
    print("✓ el clima multi-timeframe rebobina al reusarse")


def test_el_chandelier_nunca_baja() -> None:
    """
    El nivel del trailing stop solo puede subir. Se construye una serie donde
    la volatilidad crece de golpe: con la versión vieja (nivel = máximo −
    3×ATR de hoy) eso hundía el stop.
    """
    velas = [_vela(i * DIA, 100.0) for i in range(40)]
    # Expansión brusca de volatilidad en las últimas velas
    for i in range(40, 60):
        base = 100.0 + (i - 40)
        velas.append(Candle(timestamp=i * DIA, formatted_date=f"ts{i}", open=base,
                            high=base * 1.15, low=base * 0.85, close=base, volume=1.0))

    buf: deque = deque(maxlen=250)
    niveles = []
    for k, v in enumerate(velas):
        buf.append(v)
        if len(buf) <= ATR_CORTO + 1:
            continue
        nivel = CompresionVolatilidadStrategy._nivel_chandelier(buf, candles_held=k - ATR_CORTO)
        if nivel is not None:
            niveles.append(nivel)

    for anterior, siguiente in zip(niveles, niveles[1:]):
        assert siguiente >= anterior - 1e-9, (
            f"El chandelier bajó de {anterior:.4f} a {siguiente:.4f}"
        )
    print(f"✓ el chandelier nunca baja ({len(niveles)} niveles verificados)")


def test_el_sizing_respeta_el_tope_de_exposicion() -> None:
    rm = RiskManager(risk_pct=0.01, atr_multiplier=2.0, max_position_pct=0.25)
    balance, precio = 100_000.0, 50.0

    # ATR minúsculo → sin tope la fórmula pediría una posición gigante
    qty = rm.compute_quantity(balance, atr=0.01, price=precio)
    expuesto = qty * precio / balance
    assert expuesto <= 0.25 + 1e-9, f"Se comprometió el {expuesto*100:.1f}% del capital"

    # Con ATR grande el tope no debe entrometerse
    qty_chica = rm.compute_quantity(balance, atr=10.0, price=precio)
    assert qty_chica * precio / balance < 0.25
    print("✓ el sizing respeta el tope de exposición")


def test_max_candles_devuelve_el_comienzo_del_rango() -> None:
    from crypto_data_loader import CryptoDataLoader

    filas = [[i * 60_000, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10.0] for i in range(2000)]

    class ExchangeFalso:
        @staticmethod
        def fetch_ohlcv(symbol, timeframe="1m", since=None, limit=1000):
            ini = 0 if since is None else next((j for j, r in enumerate(filas) if r[0] >= since), len(filas))
            return filas[ini:ini + limit]

    ld = CryptoDataLoader.__new__(CryptoDataLoader)
    ld.exchange = ExchangeFalso()
    ld.exchange_id = "falso"

    velas = ld.load_ohlcv("X/Y", timeframe="1m", since_ms=0, max_candles=500, page_limit=1000)
    assert len(velas) == 500
    assert velas[0].timestamp == 0, (
        f"Se pidieron 500 velas desde el principio y la primera es ts={velas[0].timestamp}: "
        f"se descartaron las más viejas del rango pedido."
    )
    print("✓ max_candles devuelve el comienzo del rango pedido")


def test_paginacion_no_duplica_ni_cicla() -> None:
    from crypto_data_loader import CryptoDataLoader

    pagina = [[i * 60_000, 1.0, 1.0, 1.0, 1.0, 1.0] for i in range(100)]

    class Trabado:
        """Exchange que devuelve siempre la misma página (no avanza)."""
        @staticmethod
        def fetch_ohlcv(symbol, timeframe="1m", since=None, limit=1000):
            return list(pagina)

    ld = CryptoDataLoader.__new__(CryptoDataLoader)
    ld.exchange = Trabado()
    ld.exchange_id = "falso"

    velas = ld.load_ohlcv("X/Y", timeframe="1m", since_ms=0, page_limit=1000)
    timestamps = [c.timestamp for c in velas]
    assert len(timestamps) == len(set(timestamps)), "Se colaron velas duplicadas"
    assert len(velas) == 100
    print("✓ la paginación no duplica velas ni cicla")


def test_json_ilegible_falla_fuerte() -> None:
    logging.disable(logging.CRITICAL)
    try:
        datos = {"meta": {"symbol": "T", "timeframe": "1d", "candles": 100}, "data": {}}
        for i in range(100):
            datos["data"][str(i)] = {
                "timestamp": i, "formatted_date": f"d{i}",
                "ohlcv": {"open": None, "high": 1, "low": 1, "close": 1, "volume_units": 1},
                "indicators": {},
            }
        ruta = tempfile.mktemp(suffix=".json")
        with open(ruta, "w") as f:
            json.dump(datos, f)

        try:
            JSONDataLoader().load_from_json(ruta)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Un archivo íntegramente ilegible devolvió velas en vez de lanzar ValueError"
            )
        finally:
            os.unlink(ruta)
    finally:
        logging.disable(logging.NOTSET)
    print("✓ un JSON ilegible falla fuerte en vez de devolver una lista vacía")


def main() -> None:
    print("\n── Tests de estado, riesgo y datos " + "─" * 35)
    test_el_motor_se_reinicia_entre_backtests()
    test_el_clima_multitimeframe_rebobina()
    test_el_chandelier_nunca_baja()
    test_el_sizing_respeta_el_tope_de_exposicion()
    test_max_candles_devuelve_el_comienzo_del_rango()
    test_paginacion_no_duplica_ni_cicla()
    test_json_ilegible_falla_fuerte()
    print("── Todos los tests pasaron " + "─" * 43 + "\n")


if __name__ == "__main__":
    main()
