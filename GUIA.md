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

La misma regla se aplica **entre timeframes** — ver sección 9, que es donde más gente se resbala.

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

## 5. Las estrategias incluidas

Seis estrategias de cuatro familias distintas. La familia importa más que los parámetros: dos estrategias de la misma familia tienden a ganar y perder en los mismos momentos, así que tener variedad real es lo que hace que el desglose por clima diga algo.

| Nombre en el registro | Familia | Qué compra |
|---|---|---|
| `connors_rsi2` | Reversión a la media | Caídas extremas (RSI(2) < 10) que además tocan la Banda de Bollinger inferior, en contexto alcista |
| `pullback_tendencia` | Retroceso en tendencia | Correcciones que ya dieron vuelta, con vela de confirmación |
| `ema_crossover` | Tendencia | Cruce de EMA(20) sobre EMA(50) |
| `triple_ema` | Tendencia | Alineación de EMA(12) > EMA(50) > EMA(200) |
| `momentum_breakout` | Ruptura | Máximos de 60 velas, con régimen tendencial confirmado |
| `compresion_volatilidad` | Régimen de volatilidad | Rupturas después de que el activo se aquietó |

### `triple_ema` — Alineación de tres medias

Tres EMAs con roles separados: la **200** dice si el activo está estructuralmente sano, la **50** si la tendencia intermedia acompaña, y la **12** es el gatillo.

- **Entra** cuando EMA(12) cruza por encima de EMA(50), estando ambas ya por encima de EMA(200) y el precio también.
- **Sale** por cruce bajista de EMA(12) bajo EMA(50), por pérdida de la EMA(200) (stop estructural), o por time-stop de 60 velas.
- **Parámetros**: `EMA_GATILLO=12`, `EMA_TENDENCIA=50`, `EMA_ESTRUCTURAL=200`, `TIME_STOP_VELAS=60`.

El disparo es un **evento** (el cruce), no un estado. Si fuera un estado, la estrategia volvería a entrar en la vela siguiente a cada salida y quedaría comprada casi siempre.

### `compresion_volatilidad` — Ruptura tras compresión

No opera dirección, opera **cambio de régimen de volatilidad**. Cuando un activo se aquieta está acumulando energía; la estrategia espera esa calma y compra la ruptura.

- **Compresión** medida como `ATR(10) / ATR(50) < 0.83` (el percentil 10 del ratio observado: el 10% de velas más quietas) — la volatilidad reciente es mucho menor que la normal del activo. Se mide sobre el buffer **sin** la vela actual: si se incluyera la vela de ruptura (que por definición es grande), taparía la señal.
- **Entra** cuando, viniendo comprimido, el cierre supera el máximo de las últimas 20 velas.
- **Sale** por *chandelier stop*: un trailing stop anclado 3×ATR por debajo del máximo alcanzado desde la entrada. Sube con el precio, nunca baja.
- **Parámetros**: `ATR_CORTO=10`, `ATR_LARGO=50`, `RATIO_COMPRESION=0.83`, `RUPTURA_VELAS=20`, `CHANDELIER_ATR=3.0`, `TIME_STOP_VELAS=100`.

### `pullback_tendencia` — Retroceso con confirmación

La contracara filosófica de `connors_rsi2`, sobre el mismo evento:

- **Connors** compra *mientras* el precio cae (RSI(2) < 10). Entra barato y temprano, a veces agarra el cuchillo cayendo.
- **Esta** espera a que el precio **deje** de caer. Entra más caro, pero solo cuando el mercado ya mostró que la corrección terminó.

- **Entra** si la tendencia está intacta (precio > EMA(200), EMA(50) > EMA(200), precio > EMA(50)), hubo un RSI(14) < 40 en las últimas 5 velas, y la vela actual **cierra por encima del máximo de la anterior** — la confirmación.
- **Sale** con RSI(14) > 65 (objetivo), por pérdida de la EMA(50), o por time-stop de 30 velas.
- **Parámetros**: `RSI_RETROCESO=40`, `RSI_OBJETIVO=65`, `VENTANA_RETROCESO=5`, `TIME_STOP_VELAS=30`.

### Cómo salieron en el dataset de acciones

Corridas sobre los 13 activos de `Data_Leo/`, velas diarias, capital de $100.000 por activo, **sin optimizar un solo parámetro**:

| Estrategia | Trades | Win Rate | Expectancy | PnL |
|---|---:|---:|---:|---:|
| `ema_crossover` | 258 | 39,1% | **+0,579R** | +$156.154 |
| `triple_ema` | 221 | 36,2% | **+0,338R** | +$76.249 |
| `compresion_volatilidad` | 134 | 42,5% | **+0,205R** | +$26.737 |
| `momentum_breakout` | 203 | 42,9% | +0,111R | +$21.286 |
| `connors_rsi2` | 269 | 63,6% | +0,024R | +$6.156 |
| `pullback_tendencia` | 214 | 29,4% | −0,015R | −$3.388 |

**Cómo leer esta tabla, que es más interesante de lo que parece:**

Fijate que el orden por win rate es casi el **inverso** del orden por expectancy. `connors_rsi2` acierta 6 de cada 10 veces y casi no gana plata; `ema_crossover` falla 6 de cada 10 y es la más rentable del grupo. Eso es el comportamiento clásico de las estrategias de tendencia: muchas pérdidas chicas pagadas por pocas ganancias grandes. Es exactamente por esto que el win rate es decoración y la expectancy es el número que importa.

`pullback_tendencia` queda levemente negativa y **se deja así a propósito**: tunear parámetros hasta que dé verde sobre estas mismas 13 acciones sería sobreajustar, y el backtest dejaría de significar algo. La razón estructural de su resultado es interesante: su condición de entrada pide un RSI bajo 40 *sin* que el precio pierda la EMA(50), y en una tendencia realmente fuerte eso casi no pasa — el RSI no baja tanto. Así que el setup se auto-selecciona hacia tendencias débiles y entrecortadas, que son justo las peores para operar retrocesos. Es un buen recordatorio de que una estrategia puede estar perfectamente implementada y aun así tener una premisa que se sabotea sola.

**Advertencias sobre estos números**: son 13 acciones estadounidenses en velas diarias, no cripto. No hay optimización de parámetros (deliberadamente). Y resultados pasados sobre un dataset chico no predicen nada — sirven para comparar estrategias entre sí, no para estimar ganancias futuras.

### Lo que cambió al arreglar la matemática de los indicadores

Una auditoría encontró tres errores en el cálculo de los indicadores: el ADX devolvía el DX (le faltaba el suavizado final), el RSI usaba media simple en vez del suavizado de Wilder, y el ATR lo mismo. Al corregirlos, dos resultados que parecían buenos se desinflaron:

| Estrategia | Expectancy antes | Después | Por qué cambió |
|---|---:|---:|---|
| `momentum_breakout` | +0,570R | **+0,111R** | Depende del régimen `TRENDING_BULLISH`, que se decidía con el ADX roto |
| `compresion_volatilidad` | +0,035R | **+0,205R** | Su umbral estaba calibrado contra el ATR mal calculado; se recalibró por percentil |
| `ema_crossover` | +0,618R | +0,579R | Casi no cambia: usa las EMAs del proveedor, que estaban bien |
| `triple_ema` | +0,349R | +0,338R | Ídem |

La lección vale más que los números: **el +0,570R de `momentum_breakout` era en buena parte un artefacto de un indicador roto.** Era la segunda mejor estrategia de la tabla y pasó a ser anteúltima. Cuando el instrumento de medición está mal calibrado, las conclusiones que sacás con él son decoración — y no hay forma de saber cuáles hasta que lo arreglás y volvés a medir.

---

## 6. Cómo enchufar una estrategia nueva

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
- El **toolkit de indicadores** (sección 8) para calcular cualquier otra cosa.
- `bullish_bias` — `True` si el precio está sobre la EMA(200).
- `candles_held` — cuántas velas lleva abierta la posición.
- `regime` — el clima clásico como Enum (ver sección 7 sobre cuándo es `None`).

El texto que devuelvas en `check_exit` aparece agrupado en los reportes, así que poné nombres que sirvan para diagnosticar: `"RSI_TARGET"`, `"TRAILING_STOP"`, `"TIME_STOP"` dicen mucho más que `"salida1"`.

**Poné siempre un time-stop.** Sin él, una posición puede quedarse abierta para siempre esperando una condición que no llega.

### Paso 3 — Registrarla

Una línea en `strategy_factory.py`:

```python
from Strategys_Backtesting.mi_estrategia import MiEstrategia   # ← import

STRATEGY_REGISTRY: dict[str, type[SignalProvider]] = {
    "connors_rsi2":           RSI2Strategy,
    "momentum_breakout":      MomentumBreakoutStrategy,
    "ema_crossover":          EMACrossoverStrategy,
    "triple_ema":             TripleEMAStrategy,
    "compresion_volatilidad": CompresionVolatilidadStrategy,
    "pullback_tendencia":     PullbackTendenciaStrategy,
    "mi_estrategia":          MiEstrategia,        # ← acá
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

## 7. Cómo enchufar un pronóstico de clima nuevo

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

Se registra en `climate_factory.py` (una línea, igual que las estrategias) y se enciende con `CLIMATE_NAME` en `_test_run_cripto.py`.

**Ojo**: `_test_run.py` (el de acciones) todavía no tiene `CLIMATE_NAME` ni le pasa `climate_provider` al engine, así que usa siempre el clima por defecto. Para cambiarle el clima hay que pasárselo a mano al construir el `TradingEngine`.

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

## 8. El toolkit de indicadores

`indicators.py` — todas reciben el buffer FIFO y devuelven el valor de la vela actual (o `None` si todavía no hay historia suficiente). Ninguna mira el futuro.

| Función | Qué devuelve |
|---|---|
| `sma(fifo, period)` | Media móvil simple |
| `ema(fifo, period)` | Media móvil exponencial |
| `rsi(fifo, period)` | RSI con suavizado de Wilder |
| `atr(fifo, period)` | Average True Range con suavizado de Wilder |
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

### Cuándo usar el toolkit y cuándo el campo del Candle

Hay dos fuentes para un mismo indicador, y **no son intercambiables**:

| Fuente | Se calcula sobre | Usala para |
|---|---|---|
| Campo del `Candle` (`.ema_200`, `.rsi`, `.bb_upper`...) | Toda la serie histórica | Períodos largos |
| Función del toolkit (`ema(fifo, 200)`) | Las 250 velas del buffer | Períodos cortos, o indicadores que no existen como campo |

Los indicadores de Wilder (RSI, ATR, ADX) son **recursivos**: el valor de hoy arrastra todo el historial anterior. Por eso el toolkit los calcula sobre todo el buffer y no sobre una ventana corta — promediar solo las últimas `period` variaciones da otro indicador distinto (el RSI de Cutler, que difiere del de Wilder en ~6,6 puntos y hace que ~9% de las decisiones con umbrales 30/70 caigan del lado contrario).

El mismo principio, aplicado a la EMA: necesita alrededor de **3× su período** de historia para estabilizarse. Con el buffer de 250 velas:

- `ema(fifo, 12)` → necesita ~36 velas. **Perfecto.**
- `ema(fifo, 50)` → necesita ~150 velas. **Bien.**
- `ema(fifo, 200)` → necesitaría ~600 velas. **Mal**: el valor arranca con una semilla de las primeras 200 y solo se suaviza 50 veces. No es una EMA(200) de verdad.

La regla práctica: **si el indicador existe como campo del Candle, usá el campo**. El toolkit es para lo que no existe (como la EMA(12) de `triple_ema`) o para períodos cortos.

---

## 9. Multi-timeframe: operar en 1m, leer el clima en diaria

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

**Diaria**, como punto de partida. La EMA(200) diaria son ~6,6 meses en cripto (que opera los 365 días del año; en acciones, con ~252 ruedas, serían ~9,5 meses): es la referencia macro que define bull/bear y lo que hace reconocible un "criptoinvierno". Además cambia lento, así que el filtro no se prende y apaga cada dos días ensuciando la atribución por clima.

**4h** sirve como capa táctica (EMA200 ≈ 33 días), no como reemplazo de la diaria. **12h** no tiene ni la referencia macro de la diaria ni la reactividad de 4h.

En la metáfora: **diaria = la estación del año**, **4h = el clima de la semana**, **1m = lo que está pasando ahora**.

Es configurable a propósito — cambiá `htf_timeframe`, corré, y comparalo con datos en vez de creerle a nadie.

### Sobre el volumen de datos en 1m

8 años de BTC en 1m son **~4,2 millones de velas**. Dos consecuencias:

- **No entran en memoria como lista.** Por eso `run_backtest()` acepta también un generador: las velas se procesan de a una y nunca existe la lista completa. El buffer FIFO solo necesita 250.
- **JSON no sirve a esa escala** (~1 GB por símbolo). Para 1m hay que ir a Parquet o SQLite. El formato JSON actual está perfecto para diaria y 4h; para 1m falta implementar el almacenamiento (ver sección 13).

---

## 10. Cómo leer el reporte

Un repaso rápido de qué significa cada número, y cuál importa de verdad.

| Métrica | Qué es | Cómo leerla |
|---|---|---|
| **Win Rate** | % de operaciones ganadoras | **Engaña.** 90% de aciertos con pérdidas enormes es un sistema perdedor |
| **R-múltiplo** | Cuántas veces el riesgo inicial ganó o perdió esa operación | +2R = ganó el doble de lo que arriesgaba |
| **Expectancy** | Cuánto esperás ganar, en R, por operación promedio | **La que importa.** Si es negativa, el sistema pierde plata a la larga, tenga el win rate que tenga |
| **Max Drawdown** | La caída máxima desde un pico de la curva de capital | Cuánto dolor hay que aguantar. Un 60% de drawdown es insostenible en la práctica |
| **PnL neto** | Ganancia después de comisiones | Ya tiene descontado el 0,1% por lado |

La regla mental: **Expectancy positiva + drawdown tolerable = sistema viable.** El win rate es decoración.

### El R-múltiplo no es una unidad de riesgo (leer esto)

El `RiskManager` calcula la cantidad con `cantidad = (balance × 1%) / (ATR × 2)`. Esa fórmula da el tamaño tal que un movimiento en contra de 2×ATR cuesta el 1% del capital — **pero eso solo es cierto si la estrategia corta la pérdida en 2×ATR, y ninguna lo hace.** Usan time-stops, cruces de medias o trailing a 3×ATR.

Consecuencia: las pérdidas no están acotadas en −1R. Sobre `Data_Leo` el rango real va de **−4,10R a +2,62R**.

La lectura correcta es otra, y es igual de útil: como R = 1% del balance, **el R-múltiplo es el porcentaje de la cuenta ganado o perdido en esa operación**. Una expectancy de +0,579R significa "+0,58% de la cuenta por operación promedio". Sirve perfecto para comparar estrategias entre sí (el divisor es idéntico para todas), pero no lo leas como "gané 0,58 veces lo que arriesgué".

### El tope de exposición

Sin tope, esa misma fórmula compromete una porción enorme del capital: medido sobre `Data_Leo` daba **25,9% del capital por operación en promedio, con picos de 55,2%**, mientras el sistema anunciaba arriesgar 1%. Por eso existe `MAX_POSITION_PCT` (25% por defecto), que acota el nocional. Se activa seguido — en `compresion_volatilidad` limita el 60% de los dimensionamientos — así que si lo cambiás, los resultados se mueven.

---

## 11. Comandos

```bash
# Instalar dependencias
pip install -r requirements.txt

# Backtest de un activo (acciones, menú interactivo)
python engine.py

# Backtest masivo multi-activo — acciones (Data_Leo/)
python _test_run.py

# Backtest masivo multi-activo — cripto (descarga y cachea en Data_Cripto/)
python _test_run_cripto.py

# Tests (cada uno cubre bugs reales que ya ocurrieron)
python tests/test_multi_timeframe.py    # alineación entre timeframes
python tests/test_indicadores.py        # matemática de RSI / ATR / ADX
python tests/test_estado_y_riesgo.py    # estado, sizing y pipeline de datos
```

Salidas que genera: `trades_history.csv` (una fila por operación, con su clima), `backtest_report.txt` (reporte completo), y el resumen a color en la terminal.

---

## 12. Mapa de archivos

```
  CONTRATOS (definen las formas, no hacen nada)
    signal_provider.py       ← qué debe cumplir una estrategia
    climate_provider.py      ← qué debe cumplir un clima
    models.py                ← la clase Candle

  REGISTROS (dónde se enchufa lo nuevo)
    strategy_factory.py      ← registro de estrategias
    climate_factory.py       ← registro de climas

  PIEZAS INTERCAMBIABLES
    Strategys_Backtesting/   ← estrategias
      _plantilla.py              plantilla para copiar
      connors_rsi2.py            reversión a la media (+ el RiskManager)
      pullback_tendencia.py      retroceso en tendencia con confirmación
      ema_crossover.py           cruce EMA(20)/EMA(50)
      triple_ema.py              alineación EMA 200/50/12
      momentum_breakout.py       ruptura de máximos de 60 velas
      compresion_volatilidad.py  ruptura tras compresión de volatilidad
    Climas_Backtesting/      ← climas
      clasico_adx_ema200.py      el de siempre (ADX + EMA200)
      sin_clima.py               neutro, para estrategias sin filtro
      multi_timeframe.py         leer el clima en otro timeframe

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
      test_multi_timeframe.py   alineación entre timeframes
      test_indicadores.py       matemática de los indicadores
      test_estado_y_riesgo.py   estado, sizing y pipeline de datos
```

---

## 13. Límites conocidos

Lo que el sistema **todavía no hace**, para que nadie se lleve una sorpresa:

- **Solo opera en largo.** No hay ventas en corto.
- **Una posición por vez, por activo.** No hay pirámides ni posiciones simultáneas en el mismo activo.
- **Sin slippage.** Se asume que la orden se llena exactamente al `open`. En 1m y en activos ilíquidos esto es optimista.
- **No hay ejecución intravela.** El motor nunca mira el `.high` ni el `.low` de la vela en curso: todo stop se evalúa al CIERRE y se ejecuta al open siguiente. Esto significa que **ningún stop puede frenar un gap** — ni el chandelier de `compresion_volatilidad` ni el trailing de `momentum_breakout`. En cripto a 1 minuto, donde el precio salta, los stops son bastante más porosos de lo que parecen. Por lo mismo, el **drawdown está subestimado**: se calcula sobre cierres, y usando mínimos intradiarios sube (en COST pasa de 5,59% a 7,56%).
- **Velocidad: ~3.900 velas/segundo.** Los indicadores de Wilder son recursivos y se recalculan desde el buffer en cada vela. Para diaria y 4h es instantáneo; para 8 años de 1m serían ~18 minutos por activo. Si eso molesta, la solución es calcularlos de forma incremental guardando estado entre velas, no volver a la matemática aproximada.
- **El loader de cripto no detecta huecos** en la serie (sí deduplica velas repetidas).
- **Sin financiamiento ni fondeo.** No modela funding rates de perpetuos.
- **1m todavía no tiene almacenamiento propio.** Falta el loader de Parquet/SQLite y la descarga bulk desde `data.binance.vision` (la API REST pagina de a 1000 velas: bajar 8 años de 1m son ~4.200 requests).
- **Historia real disponible en Binance:** BTC/USDT desde agosto 2017 (~8 años), ADA desde 2018, SOL desde agosto 2020 (~5 años). No hay 10 años de cripto en Binance.
- **Panel visual pendiente.** Está previsto en Streamlit, no construido todavía.
