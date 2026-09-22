"""
risk_manager.py — Dimensionamiento de Posiciones
==================================================
Decide CUÁNTO comprar en cada operación. Es un componente de todo el
sistema (lo usa el engine para cualquier estrategia), por eso vive en su
propio módulo y no adentro de una estrategia en particular.

ADVERTENCIA — qué significa (y qué no) el "1% de riesgo"
---------------------------------------------------------
La fórmula calcula la cantidad tal que un movimiento en contra de 2×ATR
cuesta el 1% del capital. Eso es cierto SOLO si la estrategia corta la
pérdida en 2×ATR — y la mayoría de las estrategias del sistema no lo hace:
usan time-stops, cruces de medias o trailing a 3×ATR.

Consecuencia práctica: las pérdidas no están acotadas en 1R. Sobre Data_Leo
el rango real de resultados va de −4,10R a +2,62R. El R-múltiplo que
reportan los informes NO es "veces el riesgo": como R = 1% del balance, es
literalmente el PORCENTAJE DE LA CUENTA ganado o perdido en esa operación.
Sirve perfecto para comparar estrategias entre sí (el divisor es el mismo
para todas), pero no lo leas como una unidad de riesgo.

La única estrategia donde el stop está donde el sizing lo supone es
`tp_sl_fijo`, cuando su stop_loss_pct coincide con la distancia de 2×ATR.

Fórmula:
    Quantity = (Balance × risk_pct) / (ATR × atr_multiplier)
    ...acotada por (Balance × max_position_pct) / precio

Ejemplo:
    Balance = $100,000 | ATR = $13.45 | risk_pct = 1% | multiplier = 2.0
    Quantity = (100,000 × 0.01) / (13.45 × 2.0) = 1,000 / 26.9 ≈ 37 unidades
    Riesgo a 2×ATR = 37 × 13.45 × 2.0 = $995 ≈ 1% del capital ✓
"""

from __future__ import annotations

from typing import Optional

# ── Valores por defecto ───────────────────────────────────────────────────────
RISK_PCT:         float = 0.01   # Fracción del capital a arriesgar por operación (1%)
ATR_MULTIPLIER:   float = 2.0    # Distancia de riesgo supuesta, en ATR
MAX_POSITION_PCT: float = 0.25   # Tope de capital comprometido en una posición (25%)


class RiskManager:
    """
    Calcula el tamaño de posición para igualar el riesgo entre operaciones.

    Atributos
    ---------
    risk_pct         : fracción del capital a arriesgar (default 0.01)
    atr_multiplier   : distancia de riesgo supuesta, en ATR (default 2.0)
    max_position_pct : tope de exposición por posición (default 0.25)
    """

    def __init__(
        self,
        risk_pct: float = RISK_PCT,
        atr_multiplier: float = ATR_MULTIPLIER,
        max_position_pct: float = MAX_POSITION_PCT,
    ) -> None:
        self.risk_pct         = risk_pct
        self.atr_multiplier   = atr_multiplier
        self.max_position_pct = max_position_pct

    def compute_quantity(
        self,
        balance: float,
        atr: Optional[float],
        price: Optional[float] = None,
    ) -> float:
        """
        Calcula la cantidad de unidades a comprar para la próxima operación.

        Parámetros
        ----------
        balance : capital disponible ANTES de la operación
        atr     : ATR(14) de la vela de señal
        price   : precio de ejecución estimado. Necesario para aplicar el tope
                  de exposición; si no se pasa, el tope no se aplica.

        Retorna 0.0 si el ATR no está disponible o los parámetros son inválidos.
        Las cantidades no se redondean: permite fracciones, como en cripto.
        """
        if atr is None or atr <= 0 or balance <= 0:
            return 0.0

        qty = (balance * self.risk_pct) / (atr * self.atr_multiplier)

        # Sin este tope la fórmula puede comprometer una fracción enorme del
        # capital: medido sobre Data_Leo daba 25,9% por operación en promedio y
        # hasta 55,2%, mientras el sistema declaraba arriesgar 1%.
        if price is not None and price > 0:
            qty_maxima = (balance * self.max_position_pct) / price
            qty = min(qty, qty_maxima)

        return max(0.0, qty)

    def compute_risk_amount(self, balance: float) -> float:
        """Monto en dinero que se arriesga en la próxima operación: balance × risk_pct."""
        return balance * self.risk_pct
