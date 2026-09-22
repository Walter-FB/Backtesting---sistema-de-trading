"""
test_estrategias.py — Descubrimiento, parámetros, TP/SL y comisión configurable
==================================================================================
Cubre el mecanismo con el que se agregan y ajustan estrategias:

  1. Auto-descubrimiento: soltar un .py en Strategys_Backtesting/ alcanza.
     La plantilla (_plantilla.py) se ignora a propósito.
  2. Parámetros declarados (PARAMETROS): los defaults se aplican solos, un
     override cambia el comportamiento, y un nombre desconocido es un error
     (para que un typo no se vuelva un parámetro que no hace nada).
  3. Invariancia: instanciar con los defaults explícitos da exactamente las
     mismas operaciones que instanciar sin nada. Si esto se rompe, alguna
     estrategia dejó de leer self.p y volvió a una constante.
  4. La estrategia de TP/SL fijos sale por el precio que promete.
  5. La comisión es configurable y el reporte dice qué fracción del bruto
     ganado se va en comisiones.

Se corre sin pytest:
    python tests/test_estrategias.py
"""

from __future__ import annotations

import logging
import contextlib
import io
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import JSONDataLoader
from engine import TradingEngine
from models import Candle
from strategy_factory import StrategyFactory

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COST = os.path.join(RAIZ, "Data_Leo", "NASDAQ_COST", "COST_1D_3000Bars.json")


def _correr(estrategia, velas, **kw_engine):
    e = TradingEngine(strategy=estrategia, initial_balance=100_000.0, **kw_engine)
    e.tracker.save_csv = lambda filename="": ""
    e.tracker.save_txt = lambda initial_balance=0, ticker="", filename="": ""
    with contextlib.redirect_stdout(io.StringIO()):
        e.run_backtest(velas, ticker="COST")
    return e


def _vela(ts: int, o: float, c: float, rsi: float = 50.0) -> Candle:
    return Candle(timestamp=ts, formatted_date=f"ts{ts}", open=o, high=max(o, c) * 1.001,
                  low=min(o, c) * 0.999, close=c, volume=1.0, rsi=rsi)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_auto_descubrimiento() -> None:
    nombres = StrategyFactory.available_strategies()
    esperadas = {"connors_rsi2", "ema_crossover", "momentum_breakout", "triple_ema",
                 "compresion_volatilidad", "pullback_tendencia", "tp_sl_fijo"}
    faltan = esperadas - set(nombres)
    assert not faltan, f"No se descubrieron: {sorted(faltan)}"
    assert "_plantilla" not in nombres, "La plantilla no debería registrarse"
    print(f"✓ auto-descubrimiento: {len(nombres)} estrategias, sin la plantilla")


def test_parametros_declarados() -> None:
    e = StrategyFactory.create("tp_sl_fijo")
    assert e.p["take_profit_pct"] == 2.0 and e.p["stop_loss_pct"] == 1.0

    e2 = StrategyFactory.create("tp_sl_fijo", take_profit_pct=5.0)
    assert e2.p["take_profit_pct"] == 5.0 and e2.p["stop_loss_pct"] == 1.0

    try:
        StrategyFactory.create("tp_sl_fijo", take_profit=5.0)   # typo a propósito
    except ValueError as err:
        assert "take_profit" in str(err)
    else:
        raise AssertionError("Un parámetro desconocido tiene que ser un error")

    # todas las estrategias declaran defaults completos y consistentes
    for nombre in StrategyFactory.available_strategies():
        spec = StrategyFactory.parametros_de(nombre)
        inst = StrategyFactory.create(nombre)
        for k, v in spec.items():
            assert "default" in v, f"{nombre}.{k} sin default"
            assert inst.p[k] == v["default"]
            if "min" in v:
                assert v["min"] <= v["default"] <= v["max"], f"{nombre}.{k}: default fuera de rango"
    print("✓ parámetros declarados: defaults, override y typo detectado")


def test_invariancia_defaults_explicitos() -> None:
    velas = JSONDataLoader().load_from_json(COST)
    for nombre in ("triple_ema", "compresion_volatilidad", "connors_rsi2", "pullback_tendencia"):
        spec = StrategyFactory.parametros_de(nombre)
        defaults = {k: v["default"] for k, v in spec.items()}
        a = _correr(StrategyFactory.create(nombre), velas).tracker.trades
        b = _correr(StrategyFactory.create(nombre, **defaults), velas).tracker.trades
        assert [(t.entry_date, t.exit_date, t.pnl_net) for t in a] == \
               [(t.entry_date, t.exit_date, t.pnl_net) for t in b], f"{nombre}: no es invariante"
    print("✓ instanciar con defaults explícitos == instanciar sin parámetros")


def test_un_parametro_cambia_el_resultado() -> None:
    velas = JSONDataLoader().load_from_json(COST)
    corto = _correr(StrategyFactory.create("connors_rsi2", time_stop=2), velas).tracker.trades
    largo = _correr(StrategyFactory.create("connors_rsi2", time_stop=40), velas).tracker.trades
    assert corto and largo
    assert [t.exit_date for t in corto] != [t.exit_date for t in largo], \
        "Cambiar time_stop no cambió nada: la estrategia no está leyendo self.p"
    print("✓ mover un parámetro cambia las operaciones")


def test_tp_sl_fijo_sale_por_precio() -> None:
    e = StrategyFactory.create("tp_sl_fijo", take_profit_pct=2.0, stop_loss_pct=1.0, time_stop=50)

    def buffer_con_cierre_final(cierre: float) -> deque:
        # 5 velas: la de entrada (índice 0) abrió a 100. candles_held=5 apunta a ella.
        velas = [_vela(0, 100.0, 100.0)] + [_vela(i, 100.0, 100.0) for i in range(1, 4)]
        velas.append(_vela(4, 100.0, cierre))
        return deque(velas, maxlen=250)

    assert e.check_exit(buffer_con_cierre_final(102.5), candles_held=5) == "TAKE_PROFIT"
    assert e.check_exit(buffer_con_cierre_final(98.5),  candles_held=5) == "STOP_LOSS"
    assert e.check_exit(buffer_con_cierre_final(100.5), candles_held=5) is None
    assert e.check_exit(buffer_con_cierre_final(100.5), candles_held=50) == "TIME_STOP"

    # entrada: RSI por debajo del umbral, con el filtro de EMA200 apagado
    e2 = StrategyFactory.create("tp_sl_fijo", rsi_entrada=30.0, solo_sobre_ema200=False)
    assert e2.check_entry(deque([_vela(0, 100, 100, rsi=25.0)]), None, None) is True
    assert e2.check_entry(deque([_vela(0, 100, 100, rsi=35.0)]), None, None) is False
    print("✓ tp_sl_fijo sale por take profit, stop loss y tiempo")


def test_comision_configurable_y_metrica() -> None:
    velas = JSONDataLoader().load_from_json(COST)
    e = _correr(StrategyFactory.create("connors_rsi2"), velas, commission_pct=0.0007)
    assert e.tracker.trades, "sin operaciones no hay nada que verificar"

    t = e.tracker.trades[0]
    esperado = (t.entry_price + t.exit_price) * t.quantity * 0.0007
    assert abs(t.commission - esperado) < 1e-6, f"comisión {t.commission} vs esperada {esperado}"

    perf = e.tracker.get_performance(100_000.0)
    assert "comisiones_pct_del_bruto" in perf and "comisiones_total" in perf
    assert perf["comisiones_total"] == sum(x.commission for x in e.tracker.trades)

    # con la comisión al doble, la métrica sube (y las mismas operaciones ocurren)
    e2 = _correr(StrategyFactory.create("connors_rsi2"), velas, commission_pct=0.0014)
    p2 = e2.tracker.get_performance(100_000.0)
    assert p2["comisiones_pct_del_bruto"] > perf["comisiones_pct_del_bruto"]
    print(f"✓ comisión configurable; con 0,07% las comisiones son el "
          f"{perf['comisiones_pct_del_bruto']:.1f}% del bruto ganado")


def main() -> None:
    print("\n── Tests de estrategias " + "─" * 46)
    test_auto_descubrimiento()
    test_parametros_declarados()
    test_invariancia_defaults_explicitos()
    test_un_parametro_cambia_el_resultado()
    test_tp_sl_fijo_sale_por_precio()
    test_comision_configurable_y_metrica()
    print("── Todos los tests pasaron " + "─" * 43 + "\n")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)   # los tests hablan con ✓, no con el log del engine
    main()
