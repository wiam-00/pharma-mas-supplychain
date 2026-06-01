"""
agents/safety_agent.py
Agent de surveillance des péremptions — Prévention du gaspillage médicamenteux.

Responsabilités :
  1. Recevoir les données d'expiry depuis StockAgent.
  2. Classifier la gravité (CRITICAL / HIGH / MEDIUM) selon jours restants.
  3. Calculer la valeur financière en risque de gaspillage.
  4. Envoyer des alertes structurées à DecisionAgent (canal safety.alert).
  5. Maintenir un registre des batches proches de péremption pour le rapport final.

Communication :
  ← StockAgent    : ontologie pharma.safety.check
  → DecisionAgent : ontologie pharma.safety.alert
"""

import logging
from collections import defaultdict

from spade.behaviour import CyclicBehaviour
from spade.template import Template

from agents.base_agent import BaseAgent
from config import ONTOLOGY, NEAR_EXPIRY_THRESHOLD_DAYS

logger = logging.getLogger("MAS.SafetyAgent")

# ── Seuils de classification (jours restants) ─────────────────────────────────
EXPIRY_CRITICAL_DAYS = 7    # <= 7j  → action immédiate requise
EXPIRY_HIGH_DAYS     = 15   # <= 15j → action sous 48h
EXPIRY_MEDIUM_DAYS   = NEAR_EXPIRY_THRESHOLD_DAYS  # <= 30j → planifier


def _classify_expiry(days: int) -> str:
    if days <= EXPIRY_CRITICAL_DAYS:
        return "CRITICAL"
    elif days <= EXPIRY_HIGH_DAYS:
        return "HIGH"
    return "MEDIUM"


def _recommend_action(days: int, stock: int, is_critical: int) -> str:
    if days <= EXPIRY_CRITICAL_DAYS:
        return "IMMEDIATE_DISPOSAL_OR_TRANSFER"
    elif days <= EXPIRY_HIGH_DAYS and stock > 20:
        return "EMERGENCY_REDISTRIBUTION"
    elif is_critical:
        return "PRIORITY_REDISTRIBUTION"
    return "STANDARD_REDISTRIBUTION"


class SafetyAgent(BaseAgent):

    AGENT_NAME = "SafetyAgent"

    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)
        # Registre des batches signalés : batch_id → nombre d'alertes
        self._batch_registry: dict = defaultdict(int)
        self._total_waste_risk_mad: float = 0.0
        self._alerts_sent: int = 0

    # ──────────────────────────────────────────────────────────────────────────
    class ExpiryMonitorBehavior(CyclicBehaviour):
        """Surveille les péremptions et émet des alertes de prévention."""

        async def run(self):
            msg = await self.receive(timeout=15)
            if msg is None:
                return

            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            data         = envelope["payload"]
            days         = data["expiry_days"]
            stock        = data["stock_level"]
            unit_price   = data.get("unit_price", 0.0)
            is_critical  = data.get("is_critical", 0)
            batch_id     = data.get("batch_id", "UNKNOWN")
            pharmacy_id  = data["pharmacy_id"]
            drug_name    = data["drug_name"]

            severity     = _classify_expiry(days)
            action       = _recommend_action(days, stock, is_critical)
            waste_value  = round(stock * unit_price, 2)

            # Enregistrement du batch
            self.agent._batch_registry[batch_id] += 1
            self.agent._total_waste_risk_mad += waste_value if days <= EXPIRY_HIGH_DAYS else 0
            self.agent._alerts_sent += 1

            # ── Envoi vers DecisionAgent ──────────────────────────────────────
            await self.agent.send_message(
                to_key="decision",
                ontology=ONTOLOGY["SAFETY_ALERT"],
                payload={
                    "date":           data["date"],
                    "pharmacy_id":    pharmacy_id,
                    "drug_id":        data["drug_id"],
                    "drug_name":      drug_name,
                    "batch_id":       batch_id,
                    "expiry_days":    days,
                    "expiry_date":    data.get("expiry_date", "?"),
                    "stock_level":    stock,
                    "waste_value_mad":waste_value,
                    "severity":       severity,
                    "recommended_action": action,
                    "is_critical":    is_critical,
                },
                behaviour=self,
            )

            log_fn = logger.critical if severity == "CRITICAL" else logger.warning
            log_fn(
                f"[{severity}] SafetyAgent — {pharmacy_id} | {drug_name} | "
                f"Batch={batch_id} | Expiry in {days}d | "
                f"Stock={stock} units | Waste risk={waste_value:.0f} MAD | "
                f"Action={action}"
            )

        async def on_start(self):
            logger.info("[INFO] SafetyAgent — ExpiryMonitorBehavior STARTED.")

        async def on_end(self):
            logger.info(
                f"[INFO] SafetyAgent — Session report: "
                f"Alerts={self.agent._alerts_sent} | "
                f"Unique batches at risk={len(self.agent._batch_registry)} | "
                f"Total waste risk={self.agent._total_waste_risk_mad:,.0f} MAD"
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def setup(self):
        logger.info(f"[INFO] SafetyAgent online — JID: {self.jid}")
        template = Template()
        template.set_metadata("performative", "inform")
        template.set_metadata("ontology",     ONTOLOGY["SAFETY_CHECK"])
        self.add_behaviour(self.ExpiryMonitorBehavior(), template)