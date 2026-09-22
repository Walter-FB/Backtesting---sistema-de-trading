# CLAUDE.md — Traspaso completo del proyecto

> Este archivo existe para que un Claude Code **nuevo, corriendo en la máquina de Walter**,
> pueda continuar el proyecto exactamente donde lo dejó la sesión en la nube, sin perder
> nada de lo aprendido: decisiones, contratos, números de referencia, bugs que ya pasaron,
> preferencias del usuario y el backlog priorizado con diseño.
>
> Leelo entero antes de tocar código. Es largo a propósito. Después de leerlo, leé `GUIA.md`
> (la documentación "para humanos" del sistema) — este archivo es el complemento "para vos".
>
> Última sesión en la nube: commit `c864f01` en la rama `claude/modo-nube-6ubq05`
> (repo `Walter-FB/Backtesting---sistema-de-trading`). Fecha: 2026-09-22.

---

## 0. Índice

1. Para quién es esto y qué problema resuelve
2. Cómo trabajar en este proyecto (reglas del usuario y de la sesión)
3. Estado actual: qué existe, qué funciona, qué falta
4. Arquitectura y contratos (lo que no se puede romper)
5. Mapa de archivos, con qué hace cada uno
6. Los datos: formatos, esquemas, orígenes, trampas
7. Números de referencia (regresión) — si cambian sin motivo, algo se rompió
8. Decisiones tomadas y por qué
9. Bugs que ya pasaron — no los repitas
10. Cómo verificar cualquier cambio
11. El panel (Streamlit): estructura, decisiones de diseño, cómo extenderlo
12. Backlog priorizado, con diseño de cada ítem
13. El descargador de velas 1m (lo que está corriendo en paralelo)
14. Glosario en criollo
15. Comandos rápidos

---

## 1. Para quién es esto y qué problema resuelve

**Usuario**: Walter (`wberrutto@gmail.com`), argentino, habla en rioplatense ("che", "viejo",
"poronga", "tarado" con cariño). Es programador/estudiante, entiende POO (hay un PNG
"Humo aplicado a poo.png" en la raíz, es un chiste interno sobre patrones). Escribe rápido y
con typos; no hay que corregírselos.

**El destinatario real del sistema es su padre**, un trader que:
- Opera **scalping en velas de 1 minuto** con un robot propio.
- Captura en promedio **~0,15% por operación**.
- Paga **~0,07% de comisión por lado** (Binance con descuento). Es decir: ~0,14% de ida y
  vuelta contra 0,15% de captura. **Las comisiones se comen casi todo el bruto.** Walter lo
  dice con crudeza ("es un tarado mi viejo, mas del 0,15 no saca y lo hacen poronga las
  comisiones") pero lo quiere ayudar: la idea es **mostrarle con números** por qué su
  enfoque no rinde y **guiarlo hacia estrategias más coherentes**.
- "Sabe algo" de trading (según Walter). Le va a interesar **manipular TP/SL y otras
  variables** y probar. Por eso el panel tiene sliders generados desde la estrategia.

**El sistema** es un backtester / "paper trading sobre datos históricos" (NO en vivo, NO
conectado a un exchange para operar):
1. Una carpeta (`Strategys_Backtesting/`) donde se sueltan archivos `.py` con estrategias
   nuevas y aparecen solas en el panel, "cómodamente".
2. Un "pronóstico del clima" (detección de régimen de mercado) **extensible con vocabulario
   abierto** (criptoinvierno, lateral, alcista…), para que cada estrategia se pueda
   atribuir: "en qué clima juega bien".
3. Un panel visual (Streamlit + Plotly) "bonito" que presente todo.

Fue pensado primero para cripto (BTC/ETH/SOL), pero el dataset con el que se desarrolló es
de **13 acciones estadounidenses en diaria** (`Data_Leo/`), porque el entorno de la nube no
tenía salida a Binance. El código es agnóstico del activo.

---

## 2. Cómo trabajar en este proyecto

### Lo que pidió el usuario explícitamente

- **No uses agentes/subagentes.** Lo pidió textualmente ("me arrepenti no uses agentes").
  Hacé el trabajo vos, secuencialmente. Una auditoría con 5 agentes le pareció ruido.
- **"Sentido común, yo confío."** Tomá decisiones razonables sin preguntar por cada detalle.
  Preguntá solo cuando dos lecturas llevan a trabajo materialmente distinto.
- **No optimices parámetros para que el backtest dé verde.** Es una decisión de diseño
  explícita y documentada en GUIA.md §5: `pullback_tendencia` se deja levemente negativa
  a propósito. Sobreajustar contra 13 acciones destruiría el valor del backtest.
- **Honestidad brutal con los números.** Cuando una auditoría encontró que la matemática
  de los indicadores estaba mal y `momentum_breakout` pasó de +0,570R a +0,111R, se
  documentó tal cual. Si algo se desinfla, se dice. El usuario valora eso más que un
  resultado lindo.
- **No le pidas que confíe en vos para cosas de seguridad.** Cuando quiso descargar un ZIP
  y dijo "si me lo das vos confío", la respuesta correcta fue explicarle cómo verificarlo
  él mismo. Mantené eso.
- **Documentación completa y en español.** GUIA.md es larga y didáctica a propósito
  ("documenta tambien todo bien completo por favor"). Cada cosa nueva va a GUIA.md.
- **Commits con mensajes en español**, descriptivos, y push a la rama de trabajo.

### Convenciones de código

- Python 3.12, sin dependencias fuera de `requirements.txt` (`ccxt`, `streamlit`,
  `pandas`, `plotly`). Todo lo demás es stdlib.
- **Español en nombres nuevos, docstrings y comentarios** (el núcleo original está en
  inglés: `TradingEngine`, `check_entry`, etc. — se respeta lo existente, lo nuevo va en
  español: `PARAMETROS`, `parametros_de`, `_descubrir`, `correr_backtest`).
- Docstrings largos al inicio de cada módulo explicando el **por qué**, no solo el qué.
  Mirá `crypto_data_loader.py` o `signal_provider.py` como modelo.
- Comentarios con el mismo tono didáctico que el código existente. Densidad alta.
- Los tests **no usan pytest**: cada `tests/test_*.py` tiene un `main()` que imprime `✓`
  por test y se corre con `python tests/test_x.py`. Mantené ese formato (el usuario los
  corre a mano).
- `from __future__ import annotations` en todos los módulos.
- Los archivos generados (`backtest_report.txt`, `trades_history.csv`, `output.txt`) están
  versionados por historia; no importa mucho, pero no los toques a mano.

### Git

- Rama de la nube: `claude/modo-nube-6ubq05`. Localmente Walter probablemente trabaje en
  `main` o en una rama propia; preguntale (o mirá `git branch`). Si hay que mergear la rama
  de la nube a `main`, es un fast-forward limpio desde `8b7ccd9` (inicial) → `c864f01`.
- `.gitignore` tiene `.venv/`, `__pycache__/`, `*.pyc`, `Data_Cripto/`. Los `.pyc` se
  des-trackearon en el último commit; si reaparecen como modificados, algo anda mal con
  el gitignore local.
- Cuando el usuario diga "commit y push", hacelo; no crees PRs sin que lo pida.

### Entorno local (Windows)

- La máquina de Walter es Windows (`C:\Users\walte\...`). El venv se activa con
  `.venv\Scripts\activate` y el Python es `.venv\Scripts\python.exe`.
- En la nube el venv era `.venv/bin/python` (Linux). Cualquier comando de este archivo
  escrito con `/` hay que traducirlo.
- Tiene una carpeta suelta `C:\Users\walte\Desktop\papertrading` con un ZIP que descargó de
  un proveedor de datos (no se pudo inspeccionar desde la nube). Y otra carpeta
  "bot de trading" con `CONTEXTO_DATOS.md` y `data/cripto.db` (velas diarias de cripto que
  bajó otra sesión). **Ahora sí podés leerlas.** Es una de las primeras cosas útiles para
  hacer: ver qué hay ahí.

---

## 3. Estado actual

### Lo que funciona (verificado, 24 tests en verde)

| Pieza | Estado |
|---|---|
| Motor event-driven anti look-ahead (`engine.py`) | Estable. Señal al cierre, ejecución al open siguiente. Acepta `Iterable[Candle]` (streaming). |
| Estrategias con parámetros declarados (`PARAMETROS` + `self.p`) | 7 estrategias convertidas, invariancia verificada. |
| Auto-descubrimiento de estrategias | `StrategyFactory` recorre `Strategys_Backtesting/` con `pkgutil`. Sin registro manual. |
| Clima plugable (`ClimateProvider`, `ClimateFactory`) | 2 registrados (`clasico_adx_ema200`, `sin_clima`) + `MultiTimeframeClimate` que se construye a mano. |
| Toolkit de indicadores (`indicators.py`) | RSI/ATR de Wilder, ADX completo, EMA/SMA/MACD/Bollinger/cruces. Testeado contra valores conocidos. |
| RiskManager en módulo propio | Sizing por ATR con tope de exposición 25%. |
| Comisión configurable + métrica "comisiones / bruto" | En engine, tracker, reporte y panel. |
| Panel Streamlit (`dashboard.py`) | Corre, pasó `AppTest` en 3 flujos, captura tomada con Chromium. Streamlit 1.63 / Plotly 7.0. |
| Cargador JSON (`data_loader.py`) | Lee formato del proveedor. Timestamps casteados a int. JSON corrupto lanza error. |
| Cargador cripto por ccxt (`crypto_data_loader.py`) | Escrito y testeado con mocks. **Nunca se probó contra Binance real** (la nube bloqueaba la salida). Primera cosa a probar localmente. |
| Multi-timeframe (`Climas_Backtesting/multi_timeframe.py`) | Clima en diaria mientras se opera en 1m. Sin look-ahead: una vela HTF se usa solo cuando `timestamp + htf_seconds <= now_ts`. |
| GUIA.md | 14 secciones, actualizada al último commit. |

### Lo que NO existe todavía (ver §12 para el diseño)

- Loader de **SQLite** para las velas de 1m (`velas_1m.db`) — la pieza más importante
  pendiente, porque es el timeframe del padre.
- **Ejecución intravela** (stops que miren `high`/`low`): hoy todo stop se evalúa al cierre.
  En 1m con TP/SL de 0,15% esto es **inaceptable** — ver §12.2. Es probablemente lo segundo
  más importante.
- Indicadores **incrementales** para que 1m no tarde 18 min por activo.
- Panel: no expone multi-timeframe ni lee SQLite.
- "Clima v2" con los 22 campos del proveedor que hoy se descartan.
- Ventas en corto, slippage, funding.
- Walk-forward / out-of-sample.

---

## 4. Arquitectura y contratos

### 4.1 La regla de oro (no negociable)

**Nada de lo que decide el sistema en la vela N puede usar información de la vela N+1.**

Se implementa así:
- Buffer FIFO `deque(maxlen=250)` (`FIFO_MAX_LEN` en `engine.py`). Todo — indicadores,
  clima, estrategia — lee **solo el buffer**. Nunca la lista completa de velas.
- La estrategia decide **al cierre** de la vela N (`check_entry`/`check_exit` con
  `fifo[-1]` = vela actual, ya cerrada).
- La orden se ejecuta **al `open` de la vela N+1** (`_execute_entry`/`_execute_exit`).
- Los indicadores que el motor calcula (`rsi_2`, `atr_14`, `adx_14`) se escriben en
  `fifo[-1]` **después** de agregar la vela al buffer, desde el buffer.
- Los indicadores "del proveedor" (`rsi`, `ema_20/50/100/200`, `macd_*`, `bb_*`) vienen
  precalculados en el JSON. Para cripto los calcula `crypto_data_loader` de forma
  incremental sobre toda la serie (cada valor usa solo datos hasta ese punto), lo cual es
  equivalente y no viola la regla.
- El clima multi-timeframe solo usa velas del timeframe superior que ya **cerraron**
  (`timestamp + htf_seconds <= now_ts`). Una vela diaria del "hoy" no está disponible hasta
  mañana.

Si alguna vez un cambio hace que un backtest mejore *mucho* de golpe, la primera sospecha
es look-ahead, no genialidad.

### 4.2 El recorrido de una vela (`engine.run_backtest`, 9 pasos)

```
for candle in data:
  1. fifo.append(candle)
  2. compute_and_set_indicators(fifo)          # rsi_2, atr_14, adx_14 → fifo[-1]
  3. current_climate = climate_provider.detect(fifo)   # ClimateReading
  4. si hay _pending_signal y no hay posición → _execute_entry(candle)  # al OPEN de hoy
  5. si hay _pending_exit y hay posición      → _execute_exit(candle)   # al OPEN de hoy
  6. si hay posición → candles_held += 1
  7. al CIERRE de hoy:
       sin posición: strategy.check_entry(fifo, climate.regime, climate.bullish_bias)
                     → si True: _pending_signal = True; guarda atr, balance, label de clima
       con posición: strategy.check_exit(fifo, candles_held) → str|None
                     → si str: _pending_exit = True, _pending_reason = str
  8. tracker.update_equity(cash + close × qty)   # equity con mark-to-market
  9. log de progreso
al final: si hay posición → _execute_exit(last, "FIN_BACKTEST", use_close=True)
          tracker.print_report / save_csv / save_txt
```

Detalles que importan:
- **`candles_held` en la vela de ejecución vale 1** (paso 6 corre antes del paso 7). Por eso
  `tp_sl_fijo` recupera el precio de entrada con `list(fifo)[-max(candles_held, 1)].open`:
  con `candles_held=1`, `fifo[-1]` es la vela de ejecución y su `.open` es el precio pagado.
  Cualquier estrategia stateless que necesite el precio de entrada usa este truco. Si
  `candles_held > len(fifo)` la vela de entrada ya salió del buffer → sale por TIME_STOP.
- El sizing usa el ATR **de la vela de la señal** (`_signal_atr`), no el de la ejecución.
- Si `RiskManager.compute_quantity` devuelve 0 (ATR None, balance chico, precio alto), la
  señal se **descarta** y se cuenta en `engine.descartes` con un warning. Antes se perdía
  en silencio.
- `run_backtest` **resetea todo el estado** al inicio (buffer, posición, pendientes, clima).
  Un mismo engine se puede reusar para varios activos, pero el panel crea uno por activo
  igual.
- La comisión se aplica por lado: entrada `cost = open × qty × (1 + commission_pct)`,
  salida `proceeds = price × qty × (1 − commission_pct)`. `TradeRecord.commission` guarda la
  suma de ambos lados.

### 4.3 Contrato de estrategia (`signal_provider.SignalProvider`)

```python
class SignalProvider(ABC):
    PARAMETROS: Dict[str, Dict[str, Any]] = {}   # {"nombre": {"default":…, "min":…, "max":…, "step":…, "ayuda":…}}

    def __init__(self, **overrides):
        desconocidos = set(overrides) - set(self.PARAMETROS)
        if desconocidos: raise ValueError(...)          # un typo NO se convierte en no-op
        self.p = {n: s["default"] for n, s in self.PARAMETROS.items()}
        self.p.update(overrides)

    @abstractmethod
    def check_entry(self, fifo: deque, regime: Optional[MarketRegime], bullish_bias: Optional[bool]) -> bool: ...
    @abstractmethod
    def check_exit(self, fifo: deque, candles_held: int) -> Optional[str]: ...   # str = motivo de salida
```

Reglas:
- **Una clase `SignalProvider` por archivo** en `Strategys_Backtesting/`. El nombre del
  archivo es la clave (`triple_ema.py` → `"triple_ema"`). Archivos que empiezan con `_` se
  ignoran (`_plantilla.py`).
- Las estrategias **no importan `RiskManager`** ni saben de dinero. Solo señales.
- Toda constante ajustable va en `PARAMETROS` y se lee con `self.p["..."]`. Las constantes
  de módulo (`RSI2_ENTRADA = 5.0`) se mantienen solo como defaults para que el archivo se
  lea de arriba a abajo.
- `min`/`max`/`step` son opcionales; si están, el panel genera un slider; si el default es
  `bool`, un checkbox; si no hay min/max, un `number_input`.
- Los motivos de salida son strings libres en MAYÚSCULAS con guión bajo
  (`"TAKE_PROFIT"`, `"STOP_LOSS"`, `"TIME_STOP"`, `"PERDIO_EMA50"`, `"CHANDELIER"`,
  `"RSI_OBJETIVO"`…). El panel los agrupa en la pestaña "Motivos de salida".
- Si una estrategia necesita estado entre velas (trailing, ratchet), **reconstruilo desde
  el buffer** en vez de guardarlo en `self` — así sobrevive al reset del engine y a
  correr varios activos. Ejemplo: `compresion_volatilidad._nivel_chandelier` reconstruye
  el chandelier como máximo acumulado con ATR incremental de Wilder.

### 4.4 Contrato de clima (`climate_provider`)

```python
@dataclass
class ClimateReading:
    label: str                              # vocabulario ABIERTO ("CRIPTOINVIERNO" vale)
    bullish_bias: Optional[bool] = None     # True alcista / False bajista / None sin sesgo
    confidence: Optional[float] = None
    regime: Optional[MarketRegime] = None   # SOLO compatibilidad con estrategias que comparan contra el Enum
    details: dict = field(default_factory=dict)

class ClimateProvider(ABC):
    @abstractmethod
    def detect(self, fifo: deque) -> ClimateReading: ...
```

- El engine llama `detect()` una vez por vela, antes de la estrategia. `fifo` nunca está
  vacío.
- `MarketRegime` (`analysis.py`) tiene 5 estados clásicos: `RANGING_MEAN_REVERSION`,
  `TRENDING_BULLISH`, `TRENDING_BEARISH`, `HIGH_VOLATILITY_CASH`, `WAITING_FOR_DATA`.
  `clasico_adx_ema200` los produce con ADX(14) + EMA200 del proveedor.
- Un clima nuevo que no mapee al Enum deja `regime=None`. Las estrategias que comparan
  contra el Enum simplemente no operan bajo ese clima (no rompen).
- El tracker guarda `climate_label` por operación y `get_performance()["by_climate"]`
  agrupa PnL, trades, win rate y expectancy por label. Eso es la "atribución por clima".
- `ClimateFactory` sí tiene **registro manual** (`CLIMATE_REGISTRY` en `climate_factory.py`),
  a diferencia de las estrategias. Sería coherente pasarlo a auto-descubrimiento igual que
  `StrategyFactory` (ítem de backlog, chico).
- `MultiTimeframeClimate(htf_candles, inner_climate, htf_timeframe="1d")` no está en el
  registro porque necesita las velas HTF en el constructor.

### 4.5 RiskManager (`risk_manager.py`)

```python
RiskManager(risk_pct=0.01, atr_multiplier=2.0, max_position_pct=0.25)
compute_quantity(balance, atr, price=None) -> float
    qty = (balance × risk_pct) / (atr × atr_multiplier)
    si price: qty = min(qty, balance × max_position_pct / price)   # tope de exposición
compute_risk_amount(balance) -> balance × risk_pct
```

**Importante para leer reportes**: el "R-múltiplo" del tracker es `pnl / (balance × risk_pct)`,
o sea **% de la cuenta**, no el riesgo real de la operación (que con el tope de exposición
puede ser menor). Está documentado en el docstring y en GUIA §11. No lo "arregles" sin
avisar: cambia todos los números de referencia.

### 4.6 TradeTracker (`tracker_positions.py`)

- `Position` (abierta), `TradeRecord` (cerrada: entry/exit date & price, quantity,
  pnl_gross, commission, pnl_net, r_multiple, exit_reason, candles_held, climate_label).
- `get_performance(initial_balance) -> dict` con: `total_trades`, `win_rate`, `expectancy`
  (R promedio), `pnl_total`, `max_drawdown_pct` (sobre la curva de equity de cierres),
  `comisiones_total`, `comisiones_pct_del_bruto` (comisiones / suma de `pnl_gross` positivos
  × 100; `inf` si no hubo ganadores), `by_climate`, `by_exit_reason`, etc.
- `save_csv` / `save_txt` / `print_report`. El panel los anula con lambdas para no escribir
  archivos en cada corrida.

---

## 5. Mapa de archivos

```
raíz/
├── CLAUDE.md                     ← este archivo
├── GUIA.md                       ← doc principal para humanos (14 secciones, 551 líneas)
├── README.md                     ← doc original del núcleo (48hs, en inglés técnico). Desactualizado pero válido.
├── MAPA_DEL_SISTEMA.txt          ← mapa del núcleo original. Desactualizado; GUIA.md manda.
├── requirements.txt              ← ccxt, streamlit, pandas, plotly
│
├── models.py            (101)    Candle dataclass. OHLCV + indicadores del proveedor + rsi_2/atr_14/adx_14 (None hasta que el motor los calcule)
├── analysis.py          ( 29)    Enum MarketRegime (5 estados)
├── data_loader.py       (211)    JSONDataLoader.load_from_json(path) -> List[Candle]. Formato del proveedor.
├── crypto_data_loader.py(434)    CryptoDataLoader (ccxt) → mismo JSON en Data_Cripto/. Calcula indicadores "de proveedor" incrementalmente. Dedup, max_candles por cabeza.
├── indicators.py        (355)    sma, ema, rsi (Wilder), atr (Wilder), adx (Wilder completo), macd, bollinger_bands, crossed_above/below. ÚNICA implementación.
├── pronostico_del_clima.py(249)  compute_and_set_indicators(fifo) (delegando a indicators.py) + RegimeDetector clásico.
├── climate_provider.py  (104)    ClimateReading + ClimateProvider (ABC)
├── climate_factory.py   ( 82)    CLIMATE_REGISTRY manual + ClimateFactory.create / available_climates
├── signal_provider.py   (134)    SignalProvider (ABC) con PARAMETROS y self.p
├── strategy_factory.py  (113)    Auto-descubrimiento. create(name, **params), parametros_de, clase_de, available_strategies
├── risk_manager.py      (101)    RiskManager
├── tracker_positions.py (596)    Position, TradeRecord, TradeTracker (métricas, reportes, by_climate)
├── engine.py            (589)    TradingEngine. Tiene también un menú interactivo (_select_asset) si se corre directo.
├── dashboard.py         (393)    Panel Streamlit
├── _test_run.py         (421)    Runner masivo sobre Data_Leo/*_1D_*.json, reporte combinado a backtest_report.txt
├── _test_run_cripto.py  (132)    Igual pero bajando de Binance a Data_Cripto/ (nunca probado en vivo)
├── _test_analysis.py    ( 31)    Smoke test viejo del RegimeDetector
│
├── Strategys_Backtesting/        (sic, "Strategys" — no lo renombres, hay imports y docs que lo usan)
│   ├── __init__.py
│   ├── _plantilla.py    (135)    Plantilla comentada. Ignorada por el descubrimiento.
│   ├── connors_rsi2.py  (192)    Reversión a la media RSI(2). PARAMETROS: rsi2_entrada=5, rsi2_salida=70, time_stop, usar_filtro_regimen
│   ├── ema_crossover.py ( 97)    Cruce EMA50/EMA200 (golden cross). time_stop=80
│   ├── triple_ema.py    (182)    EMA12 > EMA50 > EMA200 alineadas. ema_gatillo, time_stop
│   ├── momentum_breakout.py(169) Ruptura Donchian con trailing. higher_high, donchian, trailing, time_stop
│   ├── compresion_volatilidad.py(250) ATR corto/largo < ratio → ruptura → chandelier stop ratchet. ratio_compresion=0.83
│   ├── pullback_tendencia.py(198) Retroceso RSI<40 sobre EMA50 en tendencia. Negativa a propósito.
│   └── tp_sl_fijo.py    (139)    TP/SL en %. La que va a usar el padre. take_profit_pct=2, stop_loss_pct=1, rsi_entrada=30, solo_sobre_ema200, time_stop=50
│
├── Climas_Backtesting/
│   ├── __init__.py
│   ├── clasico_adx_ema200.py (37)  ClassicRegimeClimate: envuelve RegimeDetector
│   ├── sin_clima.py          (21)  NullClimateProvider: siempre "SIN_CLIMA", sin sesgo
│   └── multi_timeframe.py   (226)  MultiTimeframeClimate
│
├── tests/                        (sin pytest; `python tests/test_x.py`)
│   ├── test_indicadores.py   (6 tests)  Wilder vs valores conocidos, ADX≠DX, bordes
│   ├── test_estado_y_riesgo.py(7 tests) reset del engine, descartes, tope de exposición, chandelier ratchet, dedup del loader, JSON corrupto
│   ├── test_multi_timeframe.py(5 tests) sin look-ahead HTF, rewind, salto temporal
│   └── test_estrategias.py   (6 tests)  descubrimiento, PARAMETROS, invariancia, tp_sl_fijo, comisión
│
├── Data_Leo/                     13 acciones diarias + carpeta 1h + Documentation.pdf del proveedor
├── Data_Cripto/                  (gitignored) cache JSON de crypto_data_loader
├── Estrategias Trading Velas Acciones Cripto.pdf   PDF de referencia de estrategias (del usuario)
├── backtest_report.txt / trades_history.csv / output.txt   salidas generadas, versionadas por historia
└── .venv/                        (gitignored)
```

---

## 6. Los datos

### 6.1 `Data_Leo/` — acciones diarias (dataset de desarrollo)

- 13 activos: `LSE_URNU, NASDAQ_CELC, NASDAQ_COST, NASDAQ_HON, NASDAQ_NBTB, NASDAQ_ODFL,
  NYSE_GWW, NYSE_LHX, NYSE_LMT, NYSE_MSCI, NYSE_NOC, NYSE_PKG, QNCCF`. Cada uno en su
  carpeta con `TICKER_1D_3000Bars.json`. Hay también `Data_Leo/1h/`.
- Comprado por Walter a un vendedor que exporta desde TradingView ("Leo"). Hay un
  `Documentation.pdf` del proveedor en la carpeta.
- **Tres archivos declaran 3000 velas en `meta` y tienen menos**: `LSE_URNU` 960,
  `QNCCF` 1107, `NASDAQ_CELC` 2107. Son activos más jóvenes, no corrupción. Lección: nunca
  confiar en un metadato; contar.
- **`Data_Leo/1h/` tiene 12 JSON VACÍOS** (`"data": {}`, 102 bytes) y al lado de cada uno un
  `.xlsx` de ~800 KB con las velas horarias reales. Si se quiere usar 1h hay que escribir
  un lector de xlsx (pandas + openpyxl) que produzca el mismo `Candle`. Nadie lo pidió aún.
- Formato:
  ```json
  {
    "meta": {"symbol": "COST", "timeframe": "1D", "candles": 3000},
    "data": {
      "<unix_ts>": {
        "timestamp": 1234567890, "formatted_date": "YYYY-MM-DD",
        "ohlcv": {"open","high","low","close","volume_units", ...},
        "indicators": {
          "rsi": {"value": ..},
          "macd": {"macd_line","signal_line","histogram"},
          "emas": {"ema_20","ema_50","ema_100","ema_200", ...},
          "bollinger_bands": {"bb_mid","bb_upper","bb_lower", ...}
        }
      }
    }
  }
  ```
- **22 campos del proveedor se descartan** al cargar (verificado contando sobre los 13
  archivos). Están en cuatro lugares del JSON de cada vela:
  - `ohlcv.volume_usd`
  - `indicators.emas.gap_ema_{20,50,100,200}_pct` (distancia % del precio a cada EMA)
  - `indicators.bollinger_bands.band_width_pct`, `gap_bb_{lower,mid,upper}_pct`
  - `price_and_volatility` (grupo aparte, hermano de `ohlcv`): `price_change_{24h,7d,14d,30d}_pct`,
    `volatility_{7d,14d,30d}`, `intraday_range_pct`
  - `volume` (grupo aparte): `volume_change_{24h,7d,14d,30d}_pct`, `volume_vs_30d_avg_pct`

  Los más útiles para un "Clima v2": `band_width_pct` (compresión), `gap_ema_200_pct`
  (distancia a la tendencia), `volatility_30d`, `volume_vs_30d_avg_pct`. Ver §12.5.
  Ojo: `meta.symbol` viene con prefijo de exchange (`"NASDAQ:COST"`).
- El timestamp se castea a `int` al cargar (venía como string a veces).

### 6.2 `Data_Cripto/` — cache de ccxt (JSON, mismo formato)

- `crypto_data_loader.fetch_and_cache(symbol, timeframe, years, force_refresh=False)`.
- Calcula EMA20/50/100/200, RSI(14), MACD, Bollinger incrementalmente y guarda en el
  mismo esquema que Data_Leo, así el resto del sistema no distingue.
- **Nunca se probó contra Binance real.** En la nube: primero SSL, después 403 del proxy.
  Los tests usan mocks del método `fetch_ohlcv`.
- Hechos de Binance verificados por conocimiento (no por request): BTC/USDT desde agosto
  2017, ETH/USDT desde agosto 2017, ADA desde 2018, SOL/USDT desde agosto 2020. REST
  devuelve 1000 velas por request. No hay "10 años de cripto" en Binance.
- `data.binance.vision` tiene ZIPs mensuales/diarios de klines (`spot/monthly/klines/
  BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip`) — más rápido para bulk. No se pudo verificar desde la
  nube. Windows marcó la descarga como "no segura" (aviso genérico de SmartScreen para
  ZIPs; el dominio es de Binance).

### 6.3 `velas_1m.db` — SQLite de 1 minuto (en descarga por otra sesión)

Otra sesión de Claude Code en la máquina de Walter está bajando **BTC/USDT, ETH/USDT,
SOL/USDT a 1m, últimos 2 años** (~1,05M velas por par, ~3,15M total, 150–250 MB) con este
esquema que yo le pedí:

```sql
CREATE TABLE IF NOT EXISTS velas (
    symbol    TEXT    NOT NULL,
    timeframe TEXT    NOT NULL,
    timestamp INTEGER NOT NULL,  -- unix EN SEGUNDOS, apertura de la vela
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
```

Requisitos que le pedí (y que vos tenés que verificar cuando lo veas): resumible,
idempotente, dedup por timestamp, cursor = MAX(ts) del lote, corte si no avanza,
reporte de huecos (no rellenados), OHLC coherente (`high >= max(o,c)`, `low <= min(o,c)`),
conteos contados y no declarados, y 20 velas al azar comparadas contra otra fuente.

**Ese archivo puede tener otro nombre/esquema si la otra sesión se desvió.** Antes de
escribir el loader, abrilo con `sqlite3` y mirá `.schema` y `SELECT symbol, COUNT(*),
MIN(timestamp), MAX(timestamp) FROM velas GROUP BY symbol`.

### 6.4 `bot de trading/data/cripto.db` — diarias de cripto (ya existe)

Walter mencionó una carpeta local "bot de trading" con `CONTEXTO_DATOS.md` y `data/cripto.db`
(velas diarias de cripto, "es a 24h"). Quiere **evaluar ese dato con el sistema** y correr
el estudio de clima de 8 años. Leé el `.md`, mirá el esquema, y adaptá el loader SQLite
para que lea las dos bases (probablemente el mismo loader con `timeframe` como parámetro).

---

## 7. Números de referencia (regresión)

Corrida sobre los 13 activos de `Data_Leo/` en diaria, $100.000 por activo, comisión
0,1% por lado (el default del engine), RiskManager por defecto, clima `clasico_adx_ema200`,
**sin optimizar nada**. Si tocás el motor, indicadores o tracker y estos cambian, tenés
que poder explicar por qué.

| Estrategia | Trades | Win Rate | Expectancy | PnL |
|---|---:|---:|---:|---:|
| `ema_crossover` | 258 | 39,1% | +0,579R | +$156.154 |
| `triple_ema` | 221 | 36,2% | +0,338R | +$76.249 |
| `compresion_volatilidad` | 134 | 42,5% | +0,205R | +$26.737 |
| `momentum_breakout` | 203 | 42,9% | +0,111R | +$21.286 |
| `connors_rsi2` | 269 | 63,6% | +0,024R | +$6.156 |
| `tp_sl_fijo` | 51 | 60,8% | +0,199R | +$10.173 |
| `pullback_tendencia` | 214 | 29,4% | −0,015R | −$3.388 |

Otros números útiles:
- `tp_sl_fijo` con SL "1%": SL efectivo promedio **−2,01%**, peor caso **−7,8%** (gap
  diario). En diaria el stop al cierre es poroso; en 1m mucho menos.
- Comisiones / bruto ganado con 0,1% por lado: `connors_rsi2` 17,3%, `ema_crossover` 3,4%.
  Con 0,07%: `connors_rsi2` 11,9% (el test lo imprime).
- Drawdown en COST: 5,59% sobre cierres, 7,56% usando mínimos intradiarios.
- Velocidad: **~3.900 velas/s**. 8 años de 1m ≈ 4,2M velas ≈ 18 min por activo. 2 años ≈ 4,5
  min. Aceptable para un runner, molesto para el panel.
- Chandelier de `compresion_volatilidad`: antes de la reescritura el nivel **bajaba el
  42,4% del tiempo** (no era un ratchet); ahora 0%.
- Umbral `ratio_compresion`: 0,70 estaba calibrado contra el ATR mal calculado; se
  recalibró a **0,83** por percentil de la distribución real del ratio.

El runner que los produce es `_test_run.py` (menú: elegir "todas"). Escribe
`backtest_report.txt`.

---

## 8. Decisiones tomadas y por qué

1. **Streamlit + Plotly** para el panel (el usuario eligió Streamlit entre opciones). No
   React, no Dash.
2. **JSON del proveedor como formato canónico** para diaria/4h; cripto se convierte a ese
   mismo formato. Para 1m, JSON no escala (3M velas) → SQLite.
3. **Auto-descubrimiento de estrategias, registro manual de climas.** Las estrategias son
   lo que el padre va a agregar; los climas los agrega Walter. Igual convendría unificar.
4. **Parámetros declarados en la clase** (`PARAMETROS`) y no en un YAML aparte: el archivo
   de la estrategia es autocontenido, se copia y listo.
5. **Typo en parámetro = error**, no ignorado. Un `take_profit=5` que no hace nada es peor
   que un crash.
6. **Un solo `indicators.py`** con Wilder correcto; `pronostico_del_clima` delega. Antes
   había 3 implementaciones distintas y 3 bugs distintos.
7. **Indicadores de período largo (EMA200) del proveedor; cortos del toolkit.** Con un
   buffer de 250, una EMA200 calculada desde el buffer no converge. Documentado en GUIA §9.
8. **RiskManager fuera de las estrategias.** Antes `connors_rsi2` lo instanciaba. Las
   estrategias solo emiten señales.
9. **Comisión default 0,1%** (Binance spot sin descuento) en el engine, pero el panel
   permite 0,07. Se eligió no bajar el default para no ser optimista por defecto.
10. **Sin optimización de parámetros** contra el dataset de desarrollo. Repetido a
    propósito.
11. **Stops evaluados al cierre, ejecutados al open** — coherente con la regla de oro pero
    poroso. Se documentó como límite conocido; cambiarlo es el ítem §12.2 y requiere
    pensarlo bien.
12. **Equity con mark-to-market** (cash + close × qty) para que el drawdown no salte al
    comprar.
13. **`max_candles` en el loader cripto corta por la cabeza** (las más antiguas), no por la
    cola: cuando pedís "las últimas N velas" querés las recientes.
14. **Paleta del panel**: validada con el método dataviz (contraste y CVD en claro y
    oscuro). Series categóricas en orden fijo: azul `#2a78d6`, naranja `#eb6834`, aqua
    `#1baf7a`, amarillo `#eda100`, magenta `#e87ba4`, verde `#008300`, violeta `#4a3aa7`,
    rojo `#e34948` (claro) — versiones oscuras en `dashboard.PALETA`. Máx 8 líneas en el
    gráfico de equity; más de 8 activos colapsa a "cartera". Etiquetas directas al final
    de línea hasta 4 series. Barras por clima con color por signo (verde/rojo), no
    por categoría.
15. **`st.cache_data` en `correr_backtest`** con todos los inputs hashables (tuplas). Mover
    un slider y volver es instantáneo.

---

## 9. Bugs que ya pasaron — no los repitas

Cada uno tiene un test que lo cubre. Si vas a tocar la zona, corré el test.

| Bug | Dónde estaba | Qué se hizo | Test |
|---|---|---|---|
| ADX devolvía el DX (faltaba el suavizado final de Wilder) | `pronostico_del_clima` | `indicators.adx` con doble suavizado | `test_indicadores` |
| RSI con media simple (Cutler) en vez de Wilder | ídem | `indicators.rsi` Wilder sobre todo el buffer | ídem |
| ATR con media simple | ídem | `indicators.atr` Wilder | ídem |
| Chandelier stop que bajaba (no era ratchet) | `compresion_volatilidad` | reconstrucción stateless como máximo acumulado | `test_estado_y_riesgo` |
| `pullback_tendencia` entraba en trades que ya cumplían la salida (92% `PERDIO_EMA50`) | estrategia | se agregó `close > ema_50` a la entrada | (regresión numérica) |
| Engine no reseteaba estado entre `run_backtest` | `engine` | reset explícito al inicio | `test_estado_y_riesgo` |
| Multi-tf no reseteaba su cursor | `multi_timeframe` | `_reiniciar()` + rewind si el tiempo retrocede | `test_multi_timeframe` |
| Off-by-one en cuándo una vela HTF está disponible | `multi_timeframe` | `timestamp + htf_seconds <= now_ts` (el test estaba mal, el código bien) | ídem |
| Señales descartadas en silencio cuando qty=0 | `engine` | `self.descartes` + warning | `test_estado_y_riesgo` |
| Sin tope de exposición (qty × price > balance) | `RiskManager` | `max_position_pct=0.25` | ídem |
| `max_candles` cortaba las velas recientes | `crypto_data_loader` | corta las antiguas | ídem |
| Páginas de ccxt solapadas → duplicados | ídem | dedup por timestamp, cursor = max(ts) | ídem |
| JSON corrupto devolvía lista vacía | `data_loader` | lanza `ValueError` | ídem |
| Timestamp como string en algunos JSON | `data_loader` | `int()` al cargar | — |
| `RiskManager` dentro de la estrategia | `connors_rsi2` | módulo propio | `test_estado_y_riesgo` |
| `.pyc` versionados ensuciando cada `git status` | repo | `git rm -r --cached __pycache__` | — |
| Streamlit 1.63: `use_container_width` deprecado, formatos de columna `$%,.0f` inválidos | `dashboard` | `width="stretch"`, `format="dollar"/"percent"` (percent espera fracción: dividir por 100) | AppTest |
| Auditor reportó "`_calc_adx ≡ DX`" con delta 0.000 — no reproducía exactamente (ventana distinta) | — | se reportó el matiz honestamente; el bug era real igual | — |

Lección meta: **una auditoría de agentes produjo hallazgos parcialmente inexactos**. Verificá
cada hallazgo reproduciéndolo antes de "arreglarlo".

---

## 10. Cómo verificar cualquier cambio

```bash
# Los 24 tests (Linux). En Windows: .venv\Scripts\python tests\test_x.py
for t in tests/*.py; do .venv/bin/python "$t"; done

# Regresión numérica de las 7 estrategias sobre Data_Leo
.venv/bin/python _test_run.py      # menú interactivo → "todas"; mirá backtest_report.txt

# El panel sin abrir el navegador (streamlit.testing)
.venv/bin/python - <<'EOF'
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("dashboard.py", default_timeout=120).run()
assert not at.exception, at.exception
at.sidebar.button[0].click().run()            # "Correr"
assert not at.exception, at.exception
print("metrics:", len(at.metric), "sliders:", len(at.sidebar.slider))
EOF

# Captura real (Playwright + Chromium): levantar streamlit en background y sacar screenshot
.venv/bin/python -m streamlit run dashboard.py --server.headless true --server.port 8501 &
# luego con playwright: page.goto("http://localhost:8501"); page.wait_for_timeout(8000); page.screenshot(...)
```

Checklist antes de commitear:
1. Los 4 archivos de tests en verde.
2. Si tocaste motor/indicadores/tracker/estrategias: la tabla de §7 no cambió, o sabés por qué.
3. Si tocaste el panel: AppTest sin excepción + una captura mirada con tus ojos.
4. GUIA.md actualizada (sección correspondiente + mapa de archivos §13 + límites §14).
5. `git status` sin `.pyc`.

---

## 11. El panel (`dashboard.py`)

### Estructura

- **Sidebar**: Datos (multiselect de activos descubiertos con glob `Data_Leo/**/*_1D_*.json`
  + `Data_Cripto/**/*.json`) → Estrategia (selectbox, default `tp_sl_fijo`; checkbox
  "Comparar todas") → Perillas (generadas por `_control_parametro` desde
  `StrategyFactory.parametros_de`) → Clima (selectbox de `ClimateFactory.available_climates`)
  → Costos y riesgo (comisión % por lado, riesgo %, × ATR, tope %, capital) → expander
  "¿Cómo agrego una estrategia?" → botón **Correr**.
- **Main**: 6 `st.metric` (PnL, expectancy, win rate, drawdown, operaciones, comisiones %
  del bruto) → banner de error si comisiones ≥50% del bruto, warning si ≥20% → gráfico de
  equity → tabs "Por clima" / "Operaciones" / "Motivos de salida" → si "Comparar todas":
  tabla con las 7 estrategias con defaults, incluyendo columna "SL efectivo" (promedio de
  pérdida real) que muestra la porosidad del stop.
- `correr_backtest(estrategia, params: tuple, rutas: tuple, clima, comision, riesgo: tuple,
  capital)` está cacheada con `@st.cache_data`; **todos los argumentos deben ser hashables**
  (por eso tuplas). Devuelve trades como dicts, equity por activo, perf.
- `_TradeVista` es un dataclass espejo de `TradeRecord` para que el cache serialice.
- Tema: `_modo()` lee `st.context.theme.type` ("light"/"dark") y elige `PALETA[modo]`.
  Los gráficos usan `_base_layout(pal, alto)` con fondo transparente, grilla hairline,
  `hovermode="x unified"`.

### Para extenderlo

- Nuevo control de parámetro: extendé `_control_parametro` (hoy: bool → checkbox;
  min/max → slider; si no → number_input). Si querés un `selectbox`, agregá `"opciones":
  [...]` al spec de `PARAMETROS` y manejalo ahí.
- Nueva fuente de datos (SQLite): `_fuentes()` devuelve `{etiqueta: ruta}`; `_cargar(ruta)`
  llama al loader. Para SQLite, la "ruta" puede ser `"sqlite://velas_1m.db#BTC/USDT@1m"`
  o una tupla; lo importante es que sea hashable y que `_cargar` sepa despacharla.
- Multi-timeframe en el panel: agregar en la sección Clima un checkbox "Leer el clima en
  diaria" que, si el activo elegido es 1m, cargue las diarias del mismo símbolo y construya
  `MultiTimeframeClimate(htf, inner, "1d")` en vez de `ClimateFactory.create(clima)`.

---

## 12. Backlog priorizado, con diseño

Orden sugerido. Los dos primeros son los que desbloquean el uso real por parte del padre.

### 12.1 Loader SQLite para 1m (y para `cripto.db` diaria) — PRIMERO

Crear `sqlite_data_loader.py`:

```python
class SQLiteDataLoader:
    def __init__(self, db_path: str): ...
    def symbols(self) -> list[tuple[str, str]]          # [(symbol, timeframe), ...]
    def load(self, symbol, timeframe, desde=None, hasta=None) -> Iterator[Candle]
        # SELECT ... WHERE symbol=? AND timeframe=? ORDER BY timestamp
        # yield Candle(...) fila a fila — el engine acepta Iterable, no cargues 1M velas en RAM
    def count(self, symbol, timeframe) -> int
    def huecos(self, symbol, timeframe, tf_seconds) -> list[tuple[int,int]]   # (ts, minutos faltantes)
```

Puntos de diseño:
- **Indicadores del proveedor** (`rsi`, `ema_*`, `macd_*`, `bb_*`) NO están en la tabla. Dos
  opciones: (a) calcularlos al vuelo incrementalmente en el loader mientras se hace yield
  (reusar `_apply_*_series` de `crypto_data_loader` refactorizadas a versión incremental),
  o (b) precalcularlos una vez y guardarlos en una tabla `indicadores` paralela. Para 1m,
  (a) es más simple y no duplica 3M filas; el costo es recalcular en cada corrida (EMA
  incremental es O(1) por vela, barato). Empezá por (a).
- Cuidado con la EMA200 en 1m: 200 minutos es poco. El filtro `solo_sobre_ema200` de
  `tp_sl_fijo` en 1m es filosóficamente distinto que en diaria. Documentalo; quizá el padre
  quiera EMA200 **diaria** vía multi-timeframe como filtro.
- El engine imprime progreso cada `LOG_EVERY_N = 100` velas (`engine.py:59`), una línea
  con colores ANSI. Con 1M velas son 10.000 líneas: hay que pasarlo a **porcentaje**
  (cada 1%) cuando `total` se conoce, y a cada N=10.000 en streaming. Es un cambio de
  5 líneas en `_log_progress`.
- Test: crear una DB temporal con 500 velas sintéticas, verificar orden, conteo, huecos y
  que `run_backtest` acepte el iterador.
- Panel: `_fuentes()` debe listar `(symbol, timeframe)` de cada `.db` encontrada
  (`*.db` en raíz y en `Data_Cripto/`).

### 12.2 Ejecución intravela (stops con `high`/`low`) — SEGUNDO

Hoy `check_exit` mira solo `close`. Con TP/SL de 0,15–1% en 1m, el precio toca el nivel
dentro de la vela y el cierre puede estar en cualquier lado; el backtest actual
**subestima las salidas por stop y sobreestima las por TP** (o al revés). Es la diferencia
entre un backtest útil y uno decorativo para scalping.

Diseño propuesto (compatible con la regla de oro):
- Nuevo contrato opcional en `SignalProvider`:
  `niveles(fifo, candles_held) -> Optional[tuple[float|None, float|None]]` que devuelve
  `(stop, take_profit)` en precio, calculados **al cierre de la vela N**.
- En el engine, paso nuevo entre 3 y 4: si hay posición y `niveles` devolvió algo en la
  vela anterior, mirar `candle.low <= stop` → salir a `stop` (o a `open` si `open < stop`,
  gap) y `candle.high >= tp` → salir a `tp` (o a `open` si `open > tp`). Si toca los dos en
  la misma vela, **asumir el peor caso (stop)** — es la convención conservadora estándar y
  hay que documentarla.
- Motivo de salida `"STOP_INTRAVELA"` / `"TP_INTRAVELA"` para distinguir en el panel.
- `tp_sl_fijo`, `momentum_breakout` (trailing) y `compresion_volatilidad` (chandelier)
  implementan `niveles`; las demás devuelven `None` y siguen como hoy.
- Slippage opcional: `slippage_pct` en el engine, aplicado en contra en cada fill. Default 0
  para no mover los números de referencia.
- Tests: vela sintética que abre 100, low 98, close 101 con stop en 99 → sale a 99 con
  STOP_INTRAVELA; gap: open 97 → sale a 97.
- Re-correr §7: `tp_sl_fijo` va a cambiar (más stops, SL efectivo ≈ 1%). Documentar el
  antes/después en GUIA §5 como se hizo con los indicadores.

### 12.3 Indicadores incrementales (velocidad en 1m)

`compute_and_set_indicators` recalcula RSI(2), ATR(14), ADX(14) de Wilder sobre el buffer
en cada vela: O(250) por vela. Para 1m conviene un `IndicadorIncremental` con estado
(avg_gain/avg_loss, atr, +DI/−DI smoothed) que se actualice en O(1) y **se resetee con el
engine**. Verificar que dé exactamente lo mismo que la versión sobre buffer (test de
igualdad con tolerancia 1e-9 sobre COST). No volver a la matemática aproximada.

### 12.4 Multi-timeframe en el panel + estudio de clima 8 años en cripto

- Exponer `MultiTimeframeClimate` en el panel (ver §11).
- Correr `clasico_adx_ema200` sobre BTC/ETH/SOL diarias (de `cripto.db` o de ccxt) y
  producir la **distribución de climas por año** y el PnL por clima de cada estrategia.
  Walter quiere ver "qué salta en este último año/2". Un gráfico de barras apiladas por año
  (% del tiempo en cada clima) en una pestaña nueva "Clima histórico".
- Elegir timeframe del clima: se recomendó **diaria** (4h/12h son ruido para régimen);
  documentado en GUIA §10.

### 12.5 Clima v2 con los campos del proveedor

Extender `data_loader` para cargar `band_width_pct`, `gap_ema_200_pct`, `volatility_30d`,
`volume_vs_30d_avg_pct` (agregar campos opcionales a `Candle`). Crear
`Climas_Backtesting/vendor_v2.py` con vocabulario nuevo (`"COMPRESION"`, `"EXPANSION"`,
`"CRIPTOINVIERNO"` = precio < EMA200 diaria por > N días y volatilidad baja, etc.).
Solo para Data_Leo mientras cripto no tenga esos campos — o calcularlos en
`crypto_data_loader`.

### 12.6 Chicos / higiene

- `ClimateFactory` con auto-descubrimiento como `StrategyFactory` (mismo patrón, 30 líneas).
- Selectbox de parámetro (`"opciones"` en `PARAMETROS`).
- Gitignore de `backtest_report.txt`, `trades_history.csv`, `output.txt`.
- `README.md` y `MAPA_DEL_SISTEMA.txt` están desactualizados: o se actualizan o se
  reducen a "ver GUIA.md".
- Botón "Exportar operaciones a CSV" en el panel.
- Ventas en corto (el engine es solo largo; el tracker asume qty > 0). No es prioridad
  salvo que el padre lo pida.
- Walk-forward: partir el dataset en train/test por fecha y mostrar las dos columnas en la
  comparativa. Es la única defensa real contra el sobreajuste cuando el padre empiece a
  mover sliders.

### 12.7 Para el padre, específicamente

Cuando esté el 1m + intravela, el experimento que Walter quiere mostrarle:
1. `tp_sl_fijo` con TP 0,15% / SL 0,15% / comisión 0,07% sobre BTC 1m → ver
   "comisiones % del bruto" (va a ser > 80%). Ese número es el argumento.
2. Mismo con TP 0,5% / SL 0,25% → ver cómo cae el % de comisiones.
3. Comparar con `ema_crossover` o `triple_ema` en 1m y en diaria.
La conclusión que Walter espera poder mostrar: **a 0,15% de captura, la comisión es el
socio mayoritario**. Que el panel lo diga con el banner rojo.

---

## 13. El descargador de 1m (contexto de la sesión paralela)

Le escribí a otra sesión de Claude Code un prompt completo para bajar BTC/ETH/SOL 1m de
2 años vía ccxt a `velas_1m.db` (esquema en §6.3). Le pedí explícitamente:
- Cursor de paginación = `max(timestamp)` del lote, no el último elemento (algunos
  exchanges no devuelven ordenado; asumir orden puede meter en loop infinito).
- Cortar si un lote no trae velas nuevas.
- Resumible por `MAX(timestamp)` por par; `INSERT OR REPLACE`.
- Reporte de huecos (los 5 más grandes), duplicados = 0, OHLC coherente = 0 violaciones.
- Nada de rellenar huecos ni metadatos que no salgan de contar.
- Comparar 20 velas al azar contra TradingView/Binance web.

Si cuando llegues el archivo ya existe: **verificá vos el reporte** (contá, buscá huecos
con `SELECT` de diferencias entre timestamps consecutivos > 60). Si hay un hueco de varios
días, esa ventana no sirve para backtestear y hay que saberlo antes de sacar conclusiones.

---

## 14. Glosario en criollo

- **Vela / candle**: OHLCV de un período. `fifo[-1]` es la actual, ya cerrada.
- **Buffer FIFO**: las últimas 250 velas. Todo se decide mirando solo eso.
- **Señal al cierre, ejecución al open**: se decide con la vela cerrada y se compra/vende
  al precio de apertura de la siguiente. Es lo que hace honesto al backtest.
- **Clima / pronóstico del clima**: régimen de mercado. Etiqueta libre + sesgo alcista/
  bajista opcional. Cada operación queda marcada con el clima de su entrada.
- **Expectancy / esperanza**: R promedio por operación. **El número que importa**, no el
  win rate. `connors_rsi2` gana 6 de 10 y casi no gana plata; `ema_crossover` pierde 6 de
  10 y es la más rentable. Tendencia = muchas pérdidas chicas, pocas ganancias grandes.
- **R-múltiplo (acá)**: PnL / (1% de la cuenta). % de cuenta, no unidad de riesgo real.
- **Comisiones / bruto**: qué parte de lo que ganaste en las operaciones ganadoras se
  fue en comisiones. > 20% amarillo, > 50% rojo. Para el padre: > 80%.
- **SL efectivo**: la pérdida promedio real de las operaciones que salieron por stop. Si
  pusiste 1% y da 2%, el stop es poroso (se evalúa al cierre).
- **Chandelier stop**: trailing stop = máximo desde la entrada − k × ATR. Solo sube.
- **Multi-timeframe (MTF)**: operar en 1m mirando el clima en diaria. La vela diaria de hoy
  no existe hasta mañana.
- **Look-ahead**: usar el futuro. El pecado capital. Todo lo raro que mejore mucho es
  sospechoso de esto.
- **Perillas**: los `PARAMETROS` de una estrategia, como los ve el padre en el panel.

---

## 15. Comandos rápidos (Windows, desde la raíz del repo)

```powershell
# Entorno
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Tests (los 4)
python tests\test_indicadores.py
python tests\test_estado_y_riesgo.py
python tests\test_multi_timeframe.py
python tests\test_estrategias.py

# Panel
streamlit run dashboard.py

# Runner masivo acciones (menú) / cripto (baja de Binance a Data_Cripto\)
python _test_run.py
python _test_run_cripto.py

# Un activo con menú
python engine.py

# Inspeccionar la base de 1m cuando exista
sqlite3 velas_1m.db ".schema"
sqlite3 velas_1m.db "SELECT symbol, COUNT(*), datetime(MIN(timestamp),'unixepoch'), datetime(MAX(timestamp),'unixepoch') FROM velas GROUP BY symbol"
```

---

## Última palabra

El proyecto está en un punto donde **todo lo que existe funciona y está testeado**, y lo
que falta está diseñado arriba. No reescribas lo que hay: extendelo. Si algo de este
archivo contradice al código, **el código manda y este archivo se corrige** — pero avisale
a Walter, porque significa que alguien tocó algo sin actualizar el traspaso.

Y cuando muestres números, mostralos con la advertencia de siempre: 13 acciones en diaria
no predicen nada sobre BTC en 1m. Sirven para comparar estrategias entre sí, no para
prometerle ganancias a nadie. Menos a un padre.
