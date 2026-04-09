Motor de Backtesting Cuantitativo — Documentación Técnica

Este sistema es un motor de ejecución para estrategias de trading desarrollado en un periodo de 48 horas. Su función principal es procesar datos históricos de mercado y ejecutar señales de entrada y salida bajo un esquema de simulación que busca evitar el sesgo de futuro o “Look-Ahead Bias”.

Implementación del Buffer Circular (FIFO):

La arquitectura del motor se basa en un buffer circular (collections.deque) con una capacidad máxima de 250 velas. En cada paso de tiempo del backtest, el sistema inserta una vela nueva en este buffer. Este diseño obliga a que todos los cálculos de indicadores y decisiones de la estrategia se realicen utilizando únicamente los datos contenidos en el buffer, impidiendo que el algoritmo acceda a precios futuros del set de datos.

Este método de "ventana deslizante" replica el flujo de datos de un entorno real, donde solo se dispone de la información actual y del historial reciente. Al limitar la visión del sistema, se garantiza que los indicadores calculados localmente sean coherentes con la cronología de los eventos.

Análisis de Mercado y Detección de Régimen:
El módulo pronostico_del_clima.py se encarga de enriquecer la vela actual con indicadores que no están presentes en la fuente de datos original, específicamente el RSI de 2 períodos(para una estrategia agresiva en concreto), el ATR de 14 y el ADX de 14. Estos valores se calculan dinámicamente cada vez que entra una vela al buffer.

Basándose en estos indicadores y en la EMA de 200 períodos provista por el JSON, el RegimeDetector clasifica el estado del mercado en cinco categorías: tendencia alcista, tendencia bajista, lateral (rango), alta volatilidad o espera de datos. Esta clasificación funciona como un filtro estructural que la estrategia utiliza para decidir si es operable o si debe permanecer fuera del mercado según las condiciones de volatilidad y tendencia.

Ejecución de Órdenes y Gestión de Riesgo:
El flujo de operaciones sigue un protocolo de ejecución estricto: una señal de entrada o salida se detecta al cierre de una vela, pero la orden se ejecuta al precio de apertura (Open) de la vela siguiente. Este procedimiento simula el tiempo de reacción necesario en una operación real y evita la ejecución a precios de cierre que ya no están disponibles. Por cada transacción realizada, el sistema descuenta automáticamente una comisión del 0.1% sobre el valor total de la operación.

La gestión de riesgo es controlada por el RiskManager, que calcula el tamaño de la posición (cantidad de unidades) en función del balance actual de la cuenta y la volatilidad medida por el ATR. El objetivo es normalizar el riesgo por operación, permitiendo que el sistema genere reportes de performance con métricas estandarizadas como el Drawdown Máximo, la Esperanza Matemática (Expectancy) y los R-Múltiplos.
