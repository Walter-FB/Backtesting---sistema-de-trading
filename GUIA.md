# Guía del Sistema

Cómo funciona, y cómo enchufar y encender cosas nuevas para testear.

---

## 1. Qué es esto, en tres párrafos

Es un **simulador de trading**. Le das velas históricas de un activo y una estrategia, y te dice qué habría pasado si esa estrategia hubiera operado ese período: cuántas operaciones hizo, cuántas ganó, cuánto perdió, y si el conjunto tiene ventaja matemática o no.

Lo que lo diferencia de sumar precios en un Excel es que **simula el paso del tiempo honestamente**. El motor recorre las velas de a una, y en cada momento solo puede ver lo que ya pasó. Nunca lo que viene. Esa restricción está construida en la arquitectura, no confiada a la buena voluntad de quien escribe la estrategia.

Arriba de eso hay una segunda idea: el **pronóstico del clima**. Antes de decidir si opera, el sistema clasifica en qué estado está el mercado (tendencia alcista, lateral, alta volatilidad...). Cada operación queda etiquetada con el clima en el que nació, así que al final del backtest podés ver no solo *si* una estrategia funciona, sino *en qué clima* funciona — que suele ser la pregunta más útil.

---

## 2. La regla de oro

Todo el sistema existe para respetar una sola regla:

> **La señal se detecta al cierre de una vela. La orden se ejecuta al open de la vela siguiente.**

Por qué importa: si detectás una señal mirando el cierre de hoy y comprás a ese mismo precio de cierre, estás comprando a un precio que ya no existe cuando tomaste la decisión. Eso es *look-ahead bias*, y es la razón número uno por la que un backtest da 300% anual y la cuenta real da pérdidas.

Cómo se garantiza acá:

- El motor usa un **buffer circular (FIFO) de 250 velas**. Tu estrategia recibe ese buffer y nada más. `fifo[-1]` es hoy, `fifo[-2]` es ayer. No existe forma de escribir `data[i+1]` porque el `data` completo no está a tu alcance.
- Cuando tu estrategia dice "entrar", el motor no compra: **anota la intención**. En la vuelta siguiente del loop compra al `open` de esa vela nueva.
- Cada operación paga **0,1% de comisión por lado** (entrada y salida), como en la vida real.

La misma regla se aplica **entre timeframes** — ver sección 8, que es donde más gente se resbala.

---

## 3. El recorrido de una vela

Esto es literalmente lo que pasa en cada vuelta del loop, en orden:

```
    Llega una vela nueva
            │
            ▼
    1. Entra al buffer FIFO ────────── (la más vieja se cae, quedan 250)
            │
            ▼
    2. Se calculan indicadores ─────── RSI(2), ATR(14), ADX(14)
            │                          desde el buffer, sin mirar el futuro
            ▼
    3. Se lee el clima ─────────────── ¿en qué estado está el mercado?
            │
            ▼
    4. Se ejecuta la entrada pendiente ── al OPEN de esta vela
            │                             (la señal era de la vela anterior)
            ▼
    5. Se ejecuta la salida pendiente ─── al OPEN de esta vela
            │
            ▼
    6. Se evalúa la estrategia ────────── al CIERRE de esta vela
            │                             genera la señal para MAÑANA
            ▼
    7. Se actualiza la curva de equity ── cash + posición a precio de mercado
```

Los pasos 4 y 5 pasan **antes** que el 6 a propósito: primero se ejecuta lo que se decidió ayer, después se decide lo de mañana.

---

## 4. Los cuatro enchufes

El motor no sabe nada de estrategias, ni de indicadores, ni de mercados. Solo orquesta. Todo lo demás son piezas intercambiables:

| Enchufe | Contrato | Dónde viven las piezas | Se elige con |
|---|---|---|---|
| **Estrategia** | `signal_provider.py` | `Strategys_Backtesting/` | `strategy_factory.py` |
| **Clima** | `climate_provider.py` | `Climas_Backtesting/` | `climate_factory.py` |
| **Datos** | — | `data_loader.py` (JSON), `crypto_data_loader.py` (exchange) | qué loader instanciás |
| **Riesgo** | — | `RiskManager` en `Strategys_Backtesting/connors_rsi2.py` | parámetros al construirlo |

Estrategia y clima son simétricos: mismo patrón, misma forma de agregar cosas nuevas. Si aprendés a agregar una, sabés agregar la otra.

---

## 5. Cómo enchufar una estrategia nueva

Cuatro pasos. Hay una plantilla lista para copiar en `Strategys_Backtesting/_plantilla.py`.

### Paso 1 — Copiar la plantilla

```bash
cp Strategys_Backtesting/_plantilla.py Strategys_Backtesting/mi_estrategia.py
```

### Paso 2 — Escribir las dos reglas

Toda estrategia responde solo dos preguntas:

```python
class MiEstrategia(SignalProvider):

    def check_entry(self, fifo, regime, bullish_bias) -> bool:
        # ¿Entro? True = comprar al open de la vela siguiente.
        # Se llama solo cuando NO hay posición abierta.
        ...

    def check_exit(self, fifo, candles_held) -> Optional[str]:
        # ¿Salgo? Devolvé un texto con la razón, o None para mantener.
        # Se llama solo cuando SÍ hay posición abierta.
        ...
```

Lo que tenés disponible adentro:

- `fifo[-1]` — la vela actual (`.open`, `.high`, `.low`, `.close`, `.volume`, más los indicadores del proveedor: `.rsi`, `.ema_20/50/100/200`, `.macd_line`, `.bb_upper/mid/lower`, y los que calcula el motor: `.rsi_2`, `.atr_14`, `.adx_14`).
- `fifo[-2]`, `fifo[-3]`... — las velas anteriores, hasta 250.
- El **toolkit de indicadores** (sección 7) para calcular cualquier otra cosa.
- `bullish_bias` — `True` si el precio está sobre la EMA(200).
- `candles_held` — cuántas velas lleva abierta la posición.
- `regime` — el clima clásico como Enum (ver sección 6 sobre cuándo es `None`).

El texto que devuelvas en `check_exit` aparece agrupado en los reportes, así que poné nombres que sirvan para diagnosticar: `"RSI_TARGET"`, `"TRAILING_STOP"`, `"TIME_STOP"` dicen mucho más que `"salida1"`.

**Poné siempre un time-stop.** Sin él, una posición puede quedarse abierta para siempre esperando una condición que no llega.

### Paso 3 — Registrarla

Una línea en `strategy_factory.py`:

```python
from Strategys_Backtesting.mi_estrategia import MiEstrategia   # ← import

STRATEGY_REGISTRY: dict[str, type[SignalProvider]] = {
    "connors_rsi2":      RSI2Strategy,
    "momentum_breakout": MomentumBreakoutStrategy,
    "ema_crossover":     EMACrossoverStrategy,
    "mi_estrategia":     MiEstrategia,        # ← acá
}
```

### Paso 4 — Encenderla

En el runner que vayas a correr, cambiás el nombre:

```python
# en _test_run.py (acciones) o _test_run_cripto.py (cripto)
STRATEGY_NAME: str = "mi_estrategia"
```

Y corrés:

```bash
python _test_run_cripto.py
```

Eso es todo. No se toca el motor nunca.

---

## 6. Cómo enchufar un pronóstico de clima nuevo

Mismo patrón, cuatro pasos iguales. Un clima responde una sola pregunta: **¿en qué estado está el mercado ahora?**

```python
# Climas_Backtesting/criptoinvierno.py
from climate_provider import ClimateProvider, ClimateReading

class ClimaCriptoinvierno(ClimateProvider):

    def detect(self, fifo) -> ClimateReading:
        actual = fifo[-1]

        if actual.ema_200 is None:
            return ClimateReading(label="SIN_DATOS")

        if actual.close < actual.ema_200 * 0.7:
            return ClimateReading(label="CRIPTOINVIERNO", bullish_bias=False)

        if actual.close > actual.ema_200:
            return ClimateReading(label="VERANO", bullish_bias=True)

        return ClimateReading(label="OTOÑO", bullish_bias=None)
```

Se registra en `climate_factory.py` (una línea, igual que las estrategias) y se enciende con `CLIMATE_NAME` en el runner.

**El vocabulario de climas es abierto.** El sistema original tenía cinco estados fijos (`TRENDING_BULLISH`, `RANGING_MEAN_REVERSION`, etc.). Ahora podés inventar los que quieras: la etiqueta es un texto libre.

Dos consecuencias prácticas:

- El campo `regime` de `ClimateReading` es solo para compatibilidad con las estrategias viejas que comparan contra el Enum clásico. Un clima nuevo lo deja en `None`, y una estrategia que dependa del Enum simplemente **no va a operar** bajo ese clima (no rompe, no opera). Si querés que una estrategia funcione con climas nuevos, comparala contra `label`.
- Si una estrategia no necesita clima, usá `"sin_clima"` — devuelve siempre neutro.

**Lo importante:** cada operación cerrada queda etiquetada con el clima en el que entró, y el reporte final te muestra el desglose. Así descubrís empíricamente en qué clima juega bien cada estrategia, en vez de declararlo de antemano:

```
🌤  RENDIMIENTO POR CLIMA
────────────────────────────────────────
HIGH_VOLATILITY_CASH    :   11 trades  │  WR  81.8%  │  PnL +$ 3,879.00  │  Exp +0.354R
RANGING_MEAN_REVERSION  :    6 trades  │  WR  66.7%  │  PnL +$   202.26  │  Exp +0.040R
TRENDING_BULLISH        :   14 trades  │  WR  35.7%  │  PnL $-3,239.42   │  Exp -0.228R
```

Leído: esta estrategia gana en volatilidad y lateral, y **pierde plata** en tendencia alcista. Eso es información accionable que el número global de la estrategia esconde.

---

## 7. El toolkit de indicadores

`indicators.py` — todas reciben el buffer FIFO y devuelven el valor de la vela actual (o `None` si todavía no hay historia suficiente). Ninguna mira el futuro.

| Función | Qué devuelve |
|---|---|
| `sma(fifo, period)` | Media móvil simple |
| `ema(fifo, period)` | Media móvil exponencial |
| `rsi(fifo, period)` | RSI de Wilder (cualquier período) |
| `atr(fifo, period)` | Average True Range — volatilidad |
| `adx(fifo, period)` | ADX — fuerza de tendencia (no dirección) |
| `macd(fifo, fast, slow, signal)` | `(línea, señal, histograma)` |
| `bollinger_bands(fifo, period, num_std)` | `(media, superior, inferior)` |
| `crossed_above(prev_a, curr_a, prev_b, curr_b)` | `True` si A cruzó por encima de B |
| `crossed_below(...)` | `True` si A cruzó por debajo de B |

Ejemplo de uso:

```python
from indicators import ema, rsi, crossed_above

rsi_14  = rsi(fifo, period=14)
ema_50  = ema(fifo, period=50)

if rsi_14 is not None and rsi_14 < 30 and fifo[-1].close > ema_50:
    return True
```

Siempre chequeá `is not None` antes de comparar: durante el calentamiento inicial no hay valor.

---

## 8. Multi-timeframe: operar en 1m, leer el clima en diaria

Ejecutar en velas de 1 minuto pero decidir el contexto con velas diarias.

### La trampa

Estás parado en la vela de 1m del **día 5 a las 10:00** y querés saber el clima diario. La tentación es mirar la vela diaria del día 5 — pero esa vela **todavía se está formando**: su cierre, su máximo y su mínimo aún no existen. Usarla es leer el futuro.

Lo correcto: la última vela diaria utilizable es la del **día 4**, la última que cerró.

### Cómo se usa

```python
from Climas_Backtesting.multi_timeframe import MultiTimeframeClimate

velas_1m = loader.fetch_and_cache("BTC/USDT", timeframe="1m", years=1)
velas_1d = loader.fetch_and_cache("BTC/USDT", timeframe="1d", years=8)

engine = TradingEngine(
    strategy         = StrategyFactory.create("mi_estrategia"),
    climate_provider = MultiTimeframeClimate(velas_1d, htf_timeframe="1d"),
)
engine.run_backtest(velas_1m, ticker="BTC_USDT")
```

El motor sigue iterando velas de 1m sin enterarse de nada: toda la alineación vive adentro del clima. Entre cierres diarios el clima **no cambia** — exactamente lo que pasaría operando en vivo.

Podés anidar cualquier clima adentro:

```python
MultiTimeframeClimate(velas_4h, htf_timeframe="4h", inner=ClimaCriptoinvierno())
```

### Qué timeframe conviene para el clima

**Diaria**, como punto de partida. La EMA(200) diaria son ~9,5 meses: es la referencia macro que define bull/bear en cripto y lo que hace reconocible un "criptoinvierno". Además cambia lento, así que el filtro no se prende y apaga cada dos días ensuciando la atribución por clima.

**4h** sirve como capa táctica (EMA200 ≈ 33 días), no como reemplazo de la diaria. **12h** no tiene ni la referencia macro de la diaria ni la reactividad de 4h.

En la metáfora: **diaria = la estación del año**, **4h = el clima de la semana**, **1m = lo que está pasando ahora**.

Es configurable a propósito — cambiá `htf_timeframe`, corré, y comparalo con datos en vez de creerle a nadie.

### Sobre el volumen de datos en 1m

8 años de BTC en 1m son **~4,2 millones de velas**. Dos consecuencias:

- **No entran en memoria como lista.** Por eso `run_backtest()` acepta también un generador: las velas se procesan de a una y nunca existe la lista completa. El buffer FIFO solo necesita 250.
- **JSON no sirve a esa escala** (~1 GB por símbolo). Para 1m hay que ir a Parquet o SQLite. El formato JSON actual está perfecto para diaria y 4h; para 1m falta implementar el almacenamiento (ver sección 11).

---

## 9. Cómo leer el reporte

Un repaso rápido de qué significa cada número, y cuál importa de verdad.

| Métrica | Qué es | Cómo leerla |
|---|---|---|
| **Win Rate** | % de operaciones ganadoras | **Engaña.** 90% de aciertos con pérdidas enormes es un sistema perdedor |
| **R-múltiplo** | Cuántas veces el riesgo inicial ganó o perdió esa operación | +2R = ganó el doble de lo que arriesgaba |
| **Expectancy** | Cuánto esperás ganar, en R, por operación promedio | **La que importa.** Si es negativa, el sistema pierde plata a la larga, tenga el win rate que tenga |
| **Max Drawdown** | La caída máxima desde un pico de la curva de capital | Cuánto dolor hay que aguantar. Un 60% de drawdown es insostenible en la práctica |
| **PnL neto** | Ganancia después de comisiones | Ya tiene descontado el 0,1% por lado |

La regla mental: **Expectancy positiva + drawdown tolerable = sistema viable.** El win rate es decoración.

Un detalle sobre el tamaño de posición: el `RiskManager` calcula cuántas unidades comprar para que **cada operación arriesgue el mismo porcentaje del capital** (1% por defecto), usando el ATR como medida de volatilidad. Fórmula: `cantidad = (balance × 1%) / (ATR × 2)`. Por eso los R-múltiplos son comparables entre operaciones y entre activos.

---

## 10. Comandos

```bash
# Instalar dependencias
pip install -r requirements.txt

# Backtest de un activo (acciones, menú interactivo)
python engine.py

# Backtest masivo multi-activo — acciones (Data_Leo/)
python _test_run.py

# Backtest masivo multi-activo — cripto (descarga y cachea en Data_Cripto/)
python _test_run_cripto.py

# Tests de alineación entre timeframes
python tests/test_multi_timeframe.py
```

Salidas que genera: `trades_history.csv` (una fila por operación, con su clima), `backtest_report.txt` (reporte completo), y el resumen a color en la terminal.

---

## 11. Mapa de archivos

```
  CONTRATOS (definen las formas, no hacen nada)
    signal_provider.py       ← qué debe cumplir una estrategia
    climate_provider.py      ← qué debe cumplir un clima
    models.py                ← la clase Candle

  REGISTROS (dónde se enchufa lo nuevo)
    strategy_factory.py      ← registro de estrategias
    climate_factory.py       ← registro de climas

  PIEZAS INTERCAMBIABLES
    Strategys_Backtesting/   ← estrategias  (_plantilla.py para copiar)
    Climas_Backtesting/      ← climas       (clásico, sin_clima, multi_timeframe)

  MOTOR Y HERRAMIENTAS
    engine.py                ← el loop. Orquesta, no decide
    indicators.py            ← toolkit de indicadores
    pronostico_del_clima.py  ← cálculo de RSI(2)/ATR/ADX + detector clásico
    tracker_positions.py     ← registro de operaciones y métricas
    analysis.py              ← los 5 estados clásicos de mercado

  DATOS
    data_loader.py           ← lee JSON (acciones y cripto cacheada)
    crypto_data_loader.py    ← baja de exchange vía ccxt y cachea a JSON
    Data_Leo/                ← acciones (provistas)
    Data_Cripto/             ← cache de cripto (se genera sola)

  RUNNERS
    _test_run.py             ← backtest masivo de acciones
    _test_run_cripto.py      ← backtest masivo de cripto
    tests/                   ← tests de correctitud
```

---

## 12. Límites conocidos

Lo que el sistema **todavía no hace**, para que nadie se lleve una sorpresa:

- **Solo opera en largo.** No hay ventas en corto.
- **Una posición por vez, por activo.** No hay pirámides ni posiciones simultáneas en el mismo activo.
- **Sin slippage.** Se asume que la orden se llena exactamente al `open`. En 1m y en activos ilíquidos esto es optimista.
- **Sin financiamiento ni fondeo.** No modela funding rates de perpetuos.
- **1m todavía no tiene almacenamiento propio.** Falta el loader de Parquet/SQLite y la descarga bulk desde `data.binance.vision` (la API REST pagina de a 1000 velas: bajar 8 años de 1m son ~4.200 requests).
- **Historia real disponible en Binance:** BTC/USDT desde agosto 2017 (~8 años), ADA desde 2018, SOL desde agosto 2020 (~5 años). No hay 10 años de cripto en Binance.
- **Panel visual pendiente.** Está previsto en Streamlit, no construido todavía.
