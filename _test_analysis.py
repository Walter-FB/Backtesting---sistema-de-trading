"""
Script de verificación rápida del módulo analysis.py.
Carga COST y corre 400 velas para ver el log [ANALYSIS].
"""
import os
from data_loader import JSONDataLoader
from engine import TradingEngine

# Buscar el primer JSON disponible en Data_Leo
DATA_DIR = os.path.join(os.path.dirname(__file__), "Data_Leo")
json_path = None
for folder in os.listdir(DATA_DIR):
    folder_path = os.path.join(DATA_DIR, folder)
    if os.path.isdir(folder_path):
        for fname in os.listdir(folder_path):
            if fname.endswith(".json"):
                json_path = os.path.join(folder_path, fname)
                break
    if json_path:
        break

print(f"Usando: {json_path}")
loader = JSONDataLoader()
candles = loader.load_from_json(json_path)

# Limitar a 400 velas para test rápido
candles = candles[:400]
print(f"Cargadas {len(candles)} velas (modo test)")

engine = TradingEngine(initial_balance=100_000.0)
engine.run_backtest(candles)
