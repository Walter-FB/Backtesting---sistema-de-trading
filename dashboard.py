"""
dashboard.py — Panel visual del backtester
============================================
Elegís datos, estrategia y clima, movés las perillas, corrés, y ves qué pasó.

Correr:
    streamlit run dashboard.py

Qué muestra
-----------
- Indicadores clave: PnL, retorno, expectancy, win rate, drawdown y — el que
  más importa para un scalper — qué porcentaje de la ganancia bruta se va en
  comisiones.
- Curva de capital, una línea por activo.
- Rendimiento por clima: en qué estado del mercado gana y pierde la estrategia.
- Tabla de operaciones y motivos de salida.
- Modo comparativo: todas las estrategias sobre los mismos datos, lado a lado.

Los parámetros de cada estrategia se leen de su declaración PARAMETROS
(ver signal_provider.py): agregar una perilla ahí la hace aparecer acá sola.
"""

from __future__ import annotations

import contextlib
import dataclasses
import glob
import io
import logging
import os
import statistics
from typing import Any, Dict, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from climate_factory import ClimateFactory
from data_loader import JSONDataLoader
from engine import TradingEngine
from risk_manager import RiskManager
from strategy_factory import StrategyFactory
from tracker_positions import TradeTracker

logging.getLogger().setLevel(logging.WARNING)

RAIZ = os.path.dirname(os.path.abspath(__file__))

# ── Paleta (validada con el método de visualización: ver GUIA.md) ─────────────
PALETA = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
        "positivo": "#2a78d6", "negativo": "#e34948",
        "texto": "#0b0b0b", "texto_2": "#52514e", "muted": "#898781",
        "grilla": "#e1e0d9", "eje": "#c3c2b7",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
        "positivo": "#3987e5", "negativo": "#e66767",
        "texto": "#ffffff", "texto_2": "#c3c2b7", "muted": "#898781",
        "grilla": "#2c2c2a", "eje": "#383835",
    },
}
MAX_LINEAS = 8   # más series que esto no se distinguen; se colapsa a una cartera


def _modo() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


# ═══════════════════════════════════════════════════════════════════════════════
# DATOS
# ═══════════════════════════════════════════════════════════════════════════════

def _fuentes() -> Dict[str, str]:
    """{etiqueta: ruta} de todos los JSON diarios disponibles."""
    rutas = sorted(glob.glob(os.path.join(RAIZ, "Data_Leo", "**", "*_1D_*.json"), recursive=True))
    rutas += sorted(glob.glob(os.path.join(RAIZ, "Data_Cripto", "**", "*.json"), recursive=True))
    return {os.path.basename(r).split("_1")[0].replace("_", "/"): r for r in rutas}


@st.cache_data(show_spinner=False)
def _cargar(ruta: str):
    return JSONDataLoader().load_from_json(ruta)


@st.cache_data(show_spinner=False)
def correr_backtest(
    estrategia: str,
    params: Tuple[Tuple[str, Any], ...],
    rutas: Tuple[Tuple[str, str], ...],
    clima: str,
    comision: float,
    riesgo: Tuple[float, float, float],
    capital: float,
) -> Dict[str, Any]:
    """Corre la estrategia sobre cada activo y devuelve todo lo que el panel necesita."""
    trades: List[dict] = []
    equity: Dict[str, Tuple[List[str], List[float]]] = {}
    curva_total: List[float] = []

    for etiqueta, ruta in rutas:
        velas = _cargar(ruta)
        motor = TradingEngine(
            strategy=StrategyFactory.create(estrategia, **dict(params)),
            climate_provider=ClimateFactory.create(clima),
            initial_balance=capital,
            commission_pct=comision,
            risk_manager=RiskManager(*riesgo),
        )
        motor.tracker.save_csv = lambda filename="": ""
        motor.tracker.save_txt = lambda initial_balance=0, ticker="", filename="": ""
        with contextlib.redirect_stdout(io.StringIO()):
            motor.run_backtest(velas, ticker=etiqueta)

        for t in motor.tracker.trades:
            trades.append(dataclasses.asdict(t))
        fechas = [v.formatted_date for v in velas]
        equity[etiqueta] = (fechas, list(motor.tracker._equity_curve))
        curva_total.extend(motor.tracker._equity_curve)

    resumen = TradeTracker()
    resumen.trades = [_TradeVista(**t) for t in trades]
    resumen._equity_curve = curva_total
    perf = resumen.get_performance(capital * max(len(rutas), 1))

    return {"trades": trades, "equity": equity, "perf": perf}


@dataclasses.dataclass
class _TradeVista:
    """Espejo liviano de TradeRecord para reconstruir métricas desde dicts cacheados."""
    ticker: str; entry_date: str; exit_date: str; entry_price: float; exit_price: float
    quantity: float; commission: float; pnl_gross: float; pnl_net: float; pnl_pct: float
    exit_reason: str; r_multiple: float; balance_after: float; climate_label: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICOS
# ═══════════════════════════════════════════════════════════════════════════════

def _base_layout(pal: dict, alto: int) -> dict:
    return dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=pal["texto_2"], size=12),
        margin=dict(l=8, r=8, t=8, b=8), height=alto,
        xaxis=dict(gridcolor=pal["grilla"], linecolor=pal["eje"], tickfont=dict(color=pal["muted"]), zeroline=False),
        yaxis=dict(gridcolor=pal["grilla"], linecolor=pal["eje"], tickfont=dict(color=pal["muted"]),
                   zeroline=False, tickformat=",.0f"),
        legend=dict(orientation="h", y=-0.15, font=dict(color=pal["texto_2"])),
        hoverlabel=dict(font=dict(family="system-ui, sans-serif")),
    )


def grafico_equity(equity: Dict[str, Tuple[List[str], List[float]]], pal: dict, capital: float) -> go.Figure:
    fig = go.Figure()
    series = list(equity.items())

    if len(series) > MAX_LINEAS:
        # Más de ocho líneas no se distinguen: se muestra la cartera completa.
        largo = min(len(v) for _, (_, v) in series)
        total = [sum(v[i] for _, (_, v) in series) for i in range(largo)]
        fechas = series[0][1][0][:largo]
        fig.add_trace(go.Scatter(x=fechas, y=total, mode="lines", name=f"Cartera ({len(series)} activos)",
                                 line=dict(color=pal["series"][0], width=2, shape="spline", smoothing=0.3)))
        fig.add_hline(y=capital * len(series), line=dict(color=pal["eje"], width=1))
    else:
        for i, (etiqueta, (fechas, valores)) in enumerate(series):
            fig.add_trace(go.Scatter(x=fechas, y=valores, mode="lines", name=etiqueta,
                                     line=dict(color=pal["series"][i], width=2)))
            if len(series) <= 4:   # etiqueta directa al final, solo con pocas series
                fig.add_annotation(x=fechas[-1], y=valores[-1], text=etiqueta, showarrow=False,
                                   xanchor="left", xshift=6, font=dict(color=pal["texto_2"], size=11))
        fig.add_hline(y=capital, line=dict(color=pal["eje"], width=1))

    fig.update_layout(**_base_layout(pal, 380), hovermode="x unified",
                      showlegend=len(series) >= 2, yaxis_title="Capital ($)")
    return fig


def grafico_por_clima(by_climate: Dict[str, dict], pal: dict) -> go.Figure:
    filas = sorted(by_climate.items(), key=lambda kv: kv[1]["total_pnl"])
    etiquetas = [k for k, _ in filas]
    valores = [v["total_pnl"] for _, v in filas]
    colores = [pal["positivo"] if v >= 0 else pal["negativo"] for v in valores]
    fig = go.Figure(go.Bar(
        x=valores, y=etiquetas, orientation="h", marker=dict(color=colores, cornerradius=4),
        width=0.55, text=[f"${v:+,.0f}" for v in valores], textposition="outside",
        textfont=dict(color=pal["texto_2"]),
        customdata=[[v["trades"], v["win_rate"], v["expectancy"]] for _, v in filas],
        hovertemplate="<b>%{y}</b><br>PnL: $%{x:,.0f}<br>%{customdata[0]} operaciones · "
                      "WR %{customdata[1]:.1f}% · Exp %{customdata[2]:+.3f}R<extra></extra>",
    ))
    fig.update_layout(**_base_layout(pal, 60 + 36 * len(filas)), showlegend=False,
                      xaxis_title="PnL neto ($)")
    fig.add_vline(x=0, line=dict(color=pal["eje"], width=1))
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLES
# ═══════════════════════════════════════════════════════════════════════════════

def _control_parametro(nombre: str, spec: dict) -> Any:
    default = spec["default"]
    ayuda = spec.get("ayuda")
    if isinstance(default, bool):
        return st.sidebar.checkbox(nombre, value=default, help=ayuda)
    if "min" in spec:
        return st.sidebar.slider(
            nombre, min_value=spec["min"], max_value=spec["max"], value=default,
            step=spec.get("step", 1 if isinstance(default, int) else 0.1), help=ayuda,
        )
    return st.sidebar.number_input(nombre, value=default, help=ayuda)


def _fmt_com(valor: float) -> str:
    return "sin ganancias" if valor == float("inf") else f"{valor:.1f}%"


# ═══════════════════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Backtester", page_icon="📈", layout="wide")
pal = PALETA[_modo()]

st.title("Backtester")
st.caption("Elegís datos, estrategia y clima · movés las perillas · corrés · ves qué pasó.")

fuentes = _fuentes()
if not fuentes:
    st.error("No hay datos: no se encontró ningún JSON en Data_Leo/ ni en Data_Cripto/.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Datos")
seleccion = st.sidebar.multiselect("Activos", list(fuentes), default=list(fuentes)[:3])

st.sidebar.header("Estrategia")
estrategias = StrategyFactory.available_strategies()
estrategia = st.sidebar.selectbox("Estrategia", estrategias, index=estrategias.index("tp_sl_fijo")
                                  if "tp_sl_fijo" in estrategias else 0)
comparar = st.sidebar.checkbox("Comparar todas las estrategias (con sus valores por defecto)")

spec_params = StrategyFactory.parametros_de(estrategia)
params: Dict[str, Any] = {}
if spec_params:
    st.sidebar.subheader("Perillas")
    for nombre, spec in spec_params.items():
        params[nombre] = _control_parametro(nombre, spec)
else:
    st.sidebar.caption("Esta estrategia no declara parámetros ajustables.")

st.sidebar.header("Clima")
clima = st.sidebar.selectbox("Pronóstico del clima", ClimateFactory.available_climates())

st.sidebar.header("Costos y riesgo")
comision = st.sidebar.number_input("Comisión por lado (%)", min_value=0.0, max_value=1.0, value=0.10,
                                   step=0.01, format="%.3f",
                                   help="Binance spot: 0,10% (0,075% pagando con BNB). Se cobra al entrar y al salir.") / 100
riesgo_pct = st.sidebar.number_input("Riesgo por operación (%)", 0.1, 10.0, 1.0, 0.1) / 100
atr_mult = st.sidebar.number_input("Distancia de riesgo (× ATR)", 0.5, 10.0, 2.0, 0.5)
tope_pct = st.sidebar.number_input("Tope de exposición (%)", 1.0, 100.0, 25.0, 1.0) / 100
capital = st.sidebar.number_input("Capital inicial por activo ($)", 1_000.0, 10_000_000.0, 100_000.0, 1_000.0)

with st.sidebar.expander("¿Cómo agrego una estrategia?"):
    st.markdown(
        "1. Copiá `Strategys_Backtesting/_plantilla.py` con otro nombre en la misma carpeta.\n"
        "2. Completá `check_entry` y `check_exit`.\n\n"
        "Eso es todo: aparece sola en la lista. Las perillas que declares en "
        "`PARAMETROS` aparecen acá arriba. Detalles en `GUIA.md`."
    )

correr = st.sidebar.button("Correr", type="primary", width="stretch")

if not seleccion:
    st.info("Elegí al menos un activo en la barra lateral.")
    st.stop()

rutas = tuple((s, fuentes[s]) for s in seleccion)
riesgo = (riesgo_pct, atr_mult, tope_pct)

if not correr and "ultimo" not in st.session_state:
    st.info("Configurá lo que quieras probar y apretá **Correr**.")
    st.stop()

# ── Modo comparativo ──────────────────────────────────────────────────────────
if comparar:
    filas = []
    with st.spinner(f"Corriendo {len(estrategias)} estrategias sobre {len(rutas)} activos…"):
        for nombre in estrategias:
            r = correr_backtest(nombre, tuple(), rutas, clima, comision, riesgo, capital)
            p, tr = r["perf"], r["trades"]
            if not p:
                filas.append({"Estrategia": nombre, "Operaciones": 0}); continue
            g = [t["pnl_pct"] for t in tr if t["pnl_net"] > 0]; l = [t["pnl_pct"] for t in tr if t["pnl_net"] <= 0]
            filas.append({
                "Estrategia": nombre, "Operaciones": p["total_trades"], "Win rate": p["win_rate"] / 100,
                "Expectancy (R)": p["expectancy"], "PnL": p["total_pnl"],
                "Comisiones / bruto": p["comisiones_pct_del_bruto"] / 100 if p["comisiones_pct_del_bruto"] != float("inf") else None,
                "Max drawdown": p["max_drawdown_pct"] / 100,
                "TP efectivo": statistics.median(g) / 100 if g else None,
                "SL efectivo": statistics.median(l) / 100 if l else None,
            })
    st.subheader("Todas las estrategias, mismos datos")
    st.caption("TP/SL efectivo = mediana del % ganado / perdido por operación. "
               "Comisiones / bruto = qué parte de lo que la estrategia gana se va en comisiones.")
    df = pd.DataFrame(filas).sort_values("Expectancy (R)", ascending=False)
    st.dataframe(df, width="stretch", hide_index=True, column_config={
        "Win rate": st.column_config.NumberColumn(format="percent"),
        "Comisiones / bruto": st.column_config.NumberColumn(format="percent"),
        "Max drawdown": st.column_config.NumberColumn(format="percent"),
        "TP efectivo": st.column_config.NumberColumn(format="percent"),
        "SL efectivo": st.column_config.NumberColumn(format="percent"),
        "Expectancy (R)": st.column_config.NumberColumn(format="%+.3f"),
        "PnL": st.column_config.NumberColumn(format="dollar"),
    })
    st.stop()

# ── Una estrategia ────────────────────────────────────────────────────────────
with st.spinner(f"Corriendo {estrategia} sobre {len(rutas)} activos…"):
    r = correr_backtest(estrategia, tuple(sorted(params.items())), rutas, clima, comision, riesgo, capital)
st.session_state["ultimo"] = True
perf, trades = r["perf"], r["trades"]

if not perf:
    st.warning("La estrategia no abrió ninguna operación con esta configuración.")
    st.stop()

# KPIs
com_pct = perf["comisiones_pct_del_bruto"]
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("PnL neto", f"${perf['total_pnl']:+,.0f}")
c2.metric("Retorno", f"{perf['total_return_pct']:+.2f}%")
c3.metric("Expectancy", f"{perf['expectancy']:+.3f} R", help="R = 1% del capital: es el % de la cuenta ganado por operación promedio")
c4.metric("Win rate", f"{perf['win_rate']:.1f}%", f"{perf['total_trades']} operaciones", delta_color="off")
c5.metric("Max drawdown", f"{perf['max_drawdown_pct']:.1f}%")
c6.metric("Comisiones / bruto", _fmt_com(com_pct),
          help="Qué porcentaje de la ganancia bruta se va en comisiones. <20% sano · >50% las comisiones se comen la estrategia")

if com_pct != float("inf"):
    if com_pct >= 50:
        st.error(f"De cada $100 que esta estrategia gana en bruto, **${com_pct:.0f} se van en comisiones**. "
                 "Así no hay estrategia que aguante: hay que capturar movimientos más grandes, no mejorar la entrada.")
    elif com_pct >= 20:
        st.warning(f"Las comisiones se llevan el {com_pct:.0f}% de la ganancia bruta. Aceptable, pero cada décima de comisión pesa.")

# Equity
st.subheader("Curva de capital")
st.plotly_chart(grafico_equity(r["equity"], pal, capital), width="stretch")

# Tabs
t_clima, t_ops, t_salidas = st.tabs(["Por clima", "Operaciones", "Motivos de salida"])

with t_clima:
    st.caption("En qué estado del mercado nacen las operaciones que ganan y las que pierden.")
    st.plotly_chart(grafico_por_clima(perf["by_climate"], pal), width="stretch")
    df_c = pd.DataFrame([{"Clima": k, "Operaciones": v["trades"], "Win rate": v["win_rate"] / 100,
                          "PnL": v["total_pnl"], "Expectancy (R)": v["expectancy"]}
                         for k, v in perf["by_climate"].items()]).sort_values("PnL", ascending=False)
    st.dataframe(df_c, width="stretch", hide_index=True, column_config={
        "Win rate": st.column_config.NumberColumn(format="percent"),
        "PnL": st.column_config.NumberColumn(format="dollar"),
        "Expectancy (R)": st.column_config.NumberColumn(format="%+.3f"),
    })

with t_ops:
    df_t = pd.DataFrame(trades)[["ticker", "entry_date", "exit_date", "entry_price", "exit_price",
                                 "pnl_net", "pnl_pct", "r_multiple", "commission", "exit_reason", "climate_label"]]
    df_t.columns = ["Activo", "Entrada", "Salida", "Precio entrada", "Precio salida",
                    "PnL", "PnL %", "R", "Comisión", "Motivo", "Clima"]
    df_t["PnL %"] = df_t["PnL %"] / 100
    st.dataframe(df_t, width="stretch", hide_index=True, column_config={
        "PnL": st.column_config.NumberColumn(format="dollar"),
        "PnL %": st.column_config.NumberColumn(format="percent"),
        "R": st.column_config.NumberColumn(format="%+.2f"),
        "Comisión": st.column_config.NumberColumn(format="dollar"),
    })

with t_salidas:
    motivos = pd.DataFrame(trades).groupby("exit_reason").agg(
        Operaciones=("pnl_net", "size"), PnL=("pnl_net", "sum"),
        Ganadoras=("pnl_net", lambda s: (s > 0).mean()),
    ).reset_index().rename(columns={"exit_reason": "Motivo", "Ganadoras": "Win rate"})
    st.dataframe(motivos.sort_values("Operaciones", ascending=False), width="stretch",
                 hide_index=True, column_config={
                     "PnL": st.column_config.NumberColumn(format="dollar"),
                     "Win rate": st.column_config.NumberColumn(format="percent"),
                 })
