"""
agents/prediction_agent.py
Agent de prévision de la demande pharmaceutique — Modèle Holt Exponential Smoothing.

Responsabilités :
  1. Recevoir les flux de demande quotidienne depuis StockAgent.
  2. Maintenir un historique glissant par couple (Pharmacy_ID, Drug_ID).
  3. Calculer une prévision à 7 jours avec Holt ES (tendance + niveau).
  4. Envoyer les prévisions à DecisionAgent (canal prediction.response).

Algorithme — Holt's Double Exponential Smoothing (sans bibliothèque externe) :
  Level_{t}  = α × x_t + (1-α) × (Level_{t-1} + Trend_{t-1})
  Trend_{t}  = β × (Level_t - Level_{t-1}) + (1-β) × Trend_{t-1}
  Forecast_h = Level_t + h × Trend_t

Communication :
  ← StockAgent    : ontologie pharma.prediction.request
  → DecisionAgent : ontologie pharma.prediction.response
"""

import logging
from collections import defaultdict, deque

from spade.behaviour import CyclicBehaviour
from spade.template import Template

from agents.base_agent import BaseAgent
from config import ONTOLOGY, FORECAST_HORIZON_DAYS

logger = logging.getLogger("MAS.PredictionAgent")

# ── Paramètres de lissage (calibrés sur données pharmaceutiques) ──────────────
ALPHA = 0.30   # Lissage du niveau   (0 = inertie totale, 1 = réactif pur)
BETA  = 0.15   # Lissage de la tendance


class _HoltModel:
    """
    Modèle de Holt Double Exponential Smoothing (implémentation pure Python).
    Une instance par couple (Pharmacy_ID, Drug_ID).
    """

    def __init__(self, alpha: float = ALPHA, beta: float = BETA, window: int = 30):
        self.alpha   = alpha
        self.beta    = beta
        self.window  = window
        self.history: deque = deque(maxlen=window)
        self.level:   float | None = None
        self.trend:   float | None = None
        self.n_obs:   int = 0

    def update(self, x: float) -> None:
        """Intègre une nouvelle observation et met à jour level + trend."""
        self.history.append(x)
        self.n_obs += 1

        if self.level is None:
            self.level = x
            self.trend = 0.0
            return

        prev_level = self.level
        self.level = self.alpha * x + (1 - self.alpha) * (self.level + self.trend)
        self.trend = self.beta * (self.level - prev_level) + (1 - self.beta) * self.trend

    def forecast(self, horizon: int = FORECAST_HORIZON_DAYS) -> list[float]:
        """
        Retourne une liste de `horizon` prévisions futures.
        Retourne [mean(history)] × horizon si insuffisamment entraîné (< 3 obs).
        """
        if self.level is None or self.n_obs < 3:
            fallback = sum(self.history) / max(len(self.history), 1)
            return [round(max(fallback, 0), 2)] * horizon

        return [
            round(max(self.level + h * self.trend, 0), 2)
            for h in range(1, horizon + 1)
        ]

    @property
    def mean_demand(self) -> float:
        return sum(self.history) / max(len(self.history), 1)

    @property
    def is_trained(self) -> bool:
        return self.n_obs >= 7


class PredictionAgent(BaseAgent):

    AGENT_NAME = "PredictionAgent"

    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)
        # Clé : (pharmacy_id, drug_id) → instance HoltModel
        self._models: dict = defaultdict(_HoltModel)

    # ──────────────────────────────────────────────────────────────────────────
    class ForecastBehavior(CyclicBehaviour):
        """Écoute les demandes de prédiction et émet les forecasts."""

        async def run(self):
            msg = await self.receive(timeout=15)
            if msg is None:
                return

            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            data     = envelope["payload"]
            ph_id    = data["pharmacy_id"]
            drug_id  = data["drug_id"]
            units    = float(data["units_sold"])
            key      = (ph_id, drug_id)

            # ── 1. Mise à jour du modèle ──────────────────────────────────────
            model = self.agent._models[key]
            model.update(units)

            # ── 2. Prévision ──────────────────────────────────────────────────
            forecasts = model.forecast(FORECAST_HORIZON_DAYS)
            total_forecast = sum(forecasts)
            avg_forecast   = total_forecast / FORECAST_HORIZON_DAYS

            # ── 3. Calcul du risque de rupture ────────────────────────────────
            current_stock = data.get("stock_level", 0)
            max_capacity  = data.get("max_capacity", 1)
            days_until_stockout = (
                int(current_stock / avg_forecast)
                if avg_forecast > 0 else 999
            )
            stockout_risk = "HIGH"   if days_until_stockout <= 3  else \
                            "MEDIUM" if days_until_stockout <= 7  else "LOW"

            # ── 4. Envoi vers DecisionAgent ───────────────────────────────────
            await self.agent.send_message(
                to_key="decision",
                ontology=ONTOLOGY["PREDICTION_RESPONSE"],
                payload={
                    "date":               data["date"],
                    "pharmacy_id":        ph_id,
                    "drug_id":            drug_id,
                    "drug_name":          data.get("drug_name", drug_id),
                    "forecast_7d":        forecasts,
                    "forecast_total_7d":  round(total_forecast, 1),
                    "forecast_avg_daily": round(avg_forecast, 2),
                    "current_stock":      current_stock,
                    "days_until_stockout":days_until_stockout,
                    "stockout_risk":      stockout_risk,
                    "model_n_obs":        model.n_obs,
                    "model_trained":      model.is_trained,
                },
                behaviour=self,
            )

            if stockout_risk != "LOW":
                logger.warning(
                    f"[WARNING] PredictionAgent — {ph_id} | {drug_id} | "
                    f"Risk={stockout_risk} | Stockout in ~{days_until_stockout}d | "
                    f"Forecast(7d)={[round(f) for f in forecasts]}"
                )

        async def on_start(self):
            logger.info("[INFO] PredictionAgent — ForecastBehavior STARTED.")

        async def on_end(self):
            trained = sum(1 for m in self.agent._models.values() if m.is_trained)
            logger.info(
                f"[INFO] PredictionAgent — ENDED. "
                f"Models: {len(self.agent._models)} | Trained: {trained}"
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def setup(self):
        logger.info(f"[INFO] PredictionAgent online — JID: {self.jid}")
        template = Template()
        template.set_metadata("performative", "inform")
        template.set_metadata("ontology",     ONTOLOGY["PREDICTION_REQUEST"])
        self.add_behaviour(self.ForecastBehavior(), template)