"""
_test_run_cripto.py — Runner multi-activo para backtest masivo sobre cripto
=============================================================================
Descarga (y cachea a disco en Data_Cripto/) años de velas de varios pares
cripto vía crypto_data_loader.py, corre un TradingEngine aislado por cada
uno (con su output individual completo e intacto) y al final imprime +
guarda el reporte combinado — incluyendo el desglose de performance por
clima, para ver en qué clima juega bien cada estrategia.

Es el equivalente cripto de _test_run.py, reutilizando exactamente el mismo
engine, el mismo TradeTracker y el mismo patrón de reporte acumulado —
la única diferencia es la fuente de datos (exchange + cache en vez de los
JSON de Data_Leo/).

Requiere: pip install ccxt   (ver crypto_data_loader.py)

Uso
---
    python _test_run_cripto.py

Para cambiar qué se testea, editá las constantes de configuración abajo:
  SYMBOLS        → pares a testear (formato ccxt: "BTC/USDT")
  TIMEFRAME      → "1d", "4h", "1h", etc.
  YEARS          → años de historial hacia atrás
  STRATEGY_NAME  → ver strategy_factory.STRATEGY_REGISTRY
  CLIMATE_NAME   → ver climate_factory.CLIMATE_REGISTRY
"""

from __future__ import annotations

import logging
import os

from climate_factory import ClimateFactory
from crypto_data_loader import CryptoDataLoader
from engine import TradingEngine
from strategy_factory import StrategyFactory
from tracker_positions import TradeTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
INITIAL_BALANCE: float = 100_000.0
TIMEFRAME:       str   = "1d"
YEARS:           int   = 10
EXCHANGE_ID:     str   = "binance"

SYMBOLS: list[str] = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]

# Estrategia y clima activos — ver los registros respectivos para las opciones.
STRATEGY_NAME: str = "ema_crossover"
CLIMATE_NAME:  str = "clasico_adx_ema200"

CACHE_DIR: str = os.path.join(os.path.dirname(__file__), "Data_Cripto")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    loader = CryptoDataLoader(exchange_id=EXCHANGE_ID)

    all_trades:   list = []
    equity_curve: list = []
    symbols_run:  list = []

    for symbol in SYMBOLS:
        logger.info(f"── {symbol} " + "─" * 50)

        try:
            candles = loader.fetch_and_cache(
                symbol=symbol, timeframe=TIMEFRAME, years=YEARS, cache_dir=CACHE_DIR,
            )
        except Exception as e:  # fallo de red, símbolo inválido, etc. — no aborta el resto
            logger.error(f"No se pudo obtener {symbol}: {e}")
            continue

        if not candles:
            logger.warning(f"Sin velas para {symbol}, se omite.")
            continue

        engine = TradingEngine(
            strategy         = StrategyFactory.create(STRATEGY_NAME),
            climate_provider = ClimateFactory.create(CLIMATE_NAME),
            initial_balance  = INITIAL_BALANCE,
        )

        # Silenciar los saves individuales — el engine llama a save_csv()/save_txt()
        # al final de cada run; los reemplazamos con no-ops en la instancia
        # (mismo truco que _test_run.py). El output de terminal individual queda intacto.
        engine.tracker.save_csv = lambda filename="": ""
        engine.tracker.save_txt = lambda initial_balance=0, ticker="", filename="": ""

        ticker = symbol.replace("/", "_")
        engine.run_backtest(candles, ticker=ticker)

        all_trades.extend(engine.tracker.trades)
        equity_curve.extend(engine.tracker._equity_curve)
        symbols_run.append(ticker)

    if not symbols_run:
        logger.error("Ningún símbolo pudo correrse. Backtest abortado.")
        return

    # ── Reporte combinado — reutiliza TradeTracker con los trades acumulados ──
    combined = TradeTracker(output_dir=os.path.dirname(os.path.abspath(__file__)))
    combined.trades = all_trades
    combined._equity_curve = equity_curve

    combined_balance = INITIAL_BALANCE * len(symbols_run)  # capital total simulado (uno por activo)

    combined.print_report(combined_balance)

    txt_path = combined.save_txt(
        initial_balance=combined_balance,
        ticker=f"CRIPTO [{', '.join(symbols_run)}]",
        filename="backtest_report_cripto.txt",
    )
    csv_path = combined.save_csv("trades_history_cripto.csv")

    logger.info(f"Reporte combinado guardado: {txt_path}")
    logger.info(f"Historial de trades guardado: {csv_path}")


if __name__ == "__main__":
    main()
