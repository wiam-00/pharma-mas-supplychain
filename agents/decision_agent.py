"""
agents/decision_agent.py
Agent Orchestrateur de Décision — Cerveau du MAS Pharma Supply Chain.

Responsabilités :
  1. Recevoir et consolider les alertes de StockAgent (stock.alert).
  2. Recevoir les prévisions de PredictionAgent (prediction.response).
  3. Recevoir les alertes de péremption de SafetyAgent (safety.alert).
  4. Pour les cas complexes (critique + multi-facteurs), déléguer à AIaaSAgent.
  5. Prendre la décision logistique finale et logger toutes les actions.
  6. Générer un rapport de session en fin de simulation.

Arbre de décision :
  stockout + critique + forecast_risk=HIGH → requête AIaaSAgent
  stockout + critique                       → EMERGENCY_TRANSFER (direct)
  stock_pct < 5% + critique                 → SUPPLIER_ORDER_EXPRESS
  safety.alert (CRITICAL)                   → WASTE_PREVENTION_CRITICAL
  safety.alert (HIGH)                       → EMERGENCY_REDISTRIBUTION
  prediction stockout_risk = HIGH           → PROACTIVE_ORDER
  stock_pct < 20%                           → SUPPLIER_ORDER_STANDARD

Communication :
  ← StockAgent      : pharma.stock.alert
  ← PredictionAgent : pharma.prediction.response
  ← SafetyAgent     : pharma.safety.alert
  ← AIaaSAgent      : pharma.aiaas.response
  → AIaaSAgent      : pharma.aiaas.request  (pour cas complexes)
"""

import json
import logging
import time
import uuid
from collections import defaultdict

from spade.behaviour import CyclicBehaviour
from spade.template import Template

from agents.base_agent import BaseAgent
from config import ONTOLOGY, CRITICAL_LOW_STOCK_PCT, LOW_STOCK_PCT, RESULTS_DIR

logger = logging.getLogger("MAS.DecisionAgent")

# ── Compteurs de session ──────────────────────────────────────────────────────
_STATS = defaultdict(int)


def _log_decision(action: str, priority: str, context: dict) -> None:
    """Logger une décision avec son contexte complet."""
    _STATS[action] += 1
    log_fn = (
        logger.critical if priority == "P1"
        else logger.warning if priority in ("P2", "P3")
        else logger.info
    )
    log_fn(
        f"[{priority}] DECISION={action} | "
        f"Pharmacy={context.get('pharmacy_id','?')} | "
        f"Drug={context.get('drug_name', context.get('drug_id','?'))} | "
        f"Stock={context.get('stock_level','?')} | "
        f"Expiry={context.get('expiry_days','?')}d | "
        f"Date={context.get('date','?')}"
    )


class DecisionAgent(BaseAgent):

    AGENT_NAME = "DecisionAgent"

    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)
        # Prévisions reçues de PredictionAgent, indexées par (pharmacy_id, drug_id)
        self._forecasts: dict  = {}
        # Réponses IA reçues de AIaaSAgent, indexées par request_id
        self._ai_responses: dict = {}
        self._session_start = time.time()

    # ──────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 1 : Traitement des alertes de stock
    # ──────────────────────────────────────────────────────────────────────────
    class HandleStockAlertBehavior(CyclicBehaviour):
        """Reçoit stock.alert et décide de l'action logistique."""

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return
            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            d           = envelope["payload"]
            pharmacy_id = d["pharmacy_id"]
            drug_id     = d["drug_id"]
            stock_pct   = d.get("stock_pct", 1.0)
            stockout    = d.get("stockout", 0)
            is_critical = d.get("is_critical", 0)
            forecast    = self.agent._forecasts.get((pharmacy_id, drug_id), {})
            forecast_risk = forecast.get("stockout_risk", "LOW")

            # ── Arbre de décision ─────────────────────────────────────────────

            # Cas 1 : Rupture + critique + forecast HIGH → déléguer à AIaaS
            if stockout and is_critical and forecast_risk == "HIGH":
                req_id = f"REQ_{uuid.uuid4().hex[:8].upper()}"
                await self.agent.send_message(
                    to_key="aiaas",
                    ontology=ONTOLOGY["AIAAS_REQUEST"],
                    payload={**d, "request_id": req_id,
                             "forecast_avg_daily": forecast.get("forecast_avg_daily", 0)},
                    performative="request",
                    behaviour=self,
                )
                _log_decision("DELEGATED_TO_AIAAS", "P1", d)

            # Cas 2 : Rupture + critique → transfert direct
            elif stockout and is_critical:
                _log_decision("EMERGENCY_TRANSFER", "P1", d)

            # CAS 3 : Stock très bas + critique → commande EXPRESS au SupplierAgent   
            elif stock_pct <= CRITICAL_LOW_STOCK_PCT and is_critical:
                _log_decision("SUPPLIER_ORDER_EXPRESS", "P2", d)
                 
                order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
                await self.agent.send_message(
                    to_key="supplier",
                    ontology=ONTOLOGY["SUPPLIER_ORDER"],
                    payload={
                        "order_id":        order_id,
                        "pharmacy_id":     d["pharmacy_id"],
                        "drug_id":         d["drug_id"],
                        "drug_name":       d["drug_name"],
                        "drug_category":   d["drug_category"],
                        "quantity_ordered": d["max_capacity"] - d["stock_level"],
                        "urgency":         "EXPRESS",
                        "unit_price":      d.get("unit_price", 0),
                        "date":            d["date"],
                    },
                    performative="request",
                    behaviour=self,
                )

   
            # CAS 4 : Stock bas non critique → commande STANDARD au SupplierAgent
            elif stock_pct <= LOW_STOCK_PCT:
                _log_decision("SUPPLIER_ORDER_STANDARD", "P3", d)
                order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
                await self.agent.send_message(
                    to_key="supplier",
                    ontology=ONTOLOGY["SUPPLIER_ORDER"],
                    payload={
                        "order_id":        order_id,
                        "pharmacy_id":     d["pharmacy_id"],
                        "drug_id":         d["drug_id"],
                        "drug_name":       d["drug_name"],
                        "drug_category":   d["drug_category"],
                        "quantity_ordered": d["max_capacity"] - d["stock_level"],
                        "urgency":         "STANDARD",
                        "unit_price":      d.get("unit_price", 0),
                        "date":            d["date"],
                    },
                    performative="request",
                    behaviour=self,
                )

            # Cas 5 : Transfert flagué dans le dataset
            elif d.get("transfer_needed", 0):
                _log_decision("INTER_PHARMACY_TRANSFER", "P2", d)

            else:
                _log_decision("MONITOR_ONLY", "P4", d)

        async def on_start(self):
            logger.info("[INFO] DecisionAgent — HandleStockAlertBehavior STARTED.")

    # ──────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 2 : Intégration des prévisions
    # ──────────────────────────────────────────────────────────────────────────
    class IntegrateForecastBehavior(CyclicBehaviour):
        """Reçoit prediction.response et met à jour le contexte de prévision."""

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return
            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            d   = envelope["payload"]
            key = (d["pharmacy_id"], d["drug_id"])
            self.agent._forecasts[key] = d

            # Alerte proactive si risque élevé détecté par la prévision
            if d["stockout_risk"] == "HIGH" and not d.get("stockout", False):
                logger.warning(
                    f"[WARNING] PROACTIVE RISK | "
                    f"{d['pharmacy_id']} | {d['drug_name']} | "
                    f"Stockout predicted in ~{d['days_until_stockout']}d | "
                    f"Forecast(7d)={[round(x) for x in d['forecast_7d']]}"
                )
                _STATS["PROACTIVE_ORDER"] += 1

        async def on_start(self):
            logger.info("[INFO] DecisionAgent — IntegrateForecastBehavior STARTED.")

    # ──────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 3 : Traitement des alertes de péremption
    # ──────────────────────────────────────────────────────────────────────────
    class HandleSafetyAlertBehavior(CyclicBehaviour):
        """Reçoit safety.alert et décide de l'action anti-gaspillage."""

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return
            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            d        = envelope["payload"]
            severity = d.get("severity", "MEDIUM")
            action   = d.get("recommended_action", "STANDARD_REDISTRIBUTION")
            priority = "P1" if severity == "CRITICAL" else "P2" if severity == "HIGH" else "P3"

            _log_decision(f"WASTE_PREVENTION_{severity}", priority, {
                **d, "stock_level": d.get("stock_level"),
                "expiry_days": d.get("expiry_days"),
            })
            logger.info(
                f"[INFO] DecisionAgent — Safety action: {action} | "
                f"Waste risk={d.get('waste_value_mad', 0):.0f} MAD"
            )

        async def on_start(self):
            logger.info("[INFO] DecisionAgent — HandleSafetyAlertBehavior STARTED.")

    # ──────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 4 : Réception des réponses IA
    # ──────────────────────────────────────────────────────────────────────────
    class ReceiveAIResponseBehavior(CyclicBehaviour):
        """Reçoit aiaas.response et applique la recommandation IA."""

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return
            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            d      = envelope["payload"]
            rec    = d.get("recommendation", {})
            source = d.get("source", "?")

            logger.info(
                f"[INFO] AI RECOMMENDATION received [{source}] | "
                f"Request={d.get('request_id')} | "
                f"Decision={rec.get('decision')} | "
                f"Confidence={rec.get('confidence', 0):.0%} | "
                f"Urgency={rec.get('urgency_hours')}h | "
                f"Qty={rec.get('recommended_qty')} | "
                f"Justification: {rec.get('justification')}"
            )
            self.agent._ai_responses[d.get("request_id")] = rec
            _STATS["AI_DECISIONS_APPLIED"] += 1

        async def on_start(self):
            logger.info("[INFO] DecisionAgent — ReceiveAIResponseBehavior STARTED.")

        async def on_end(self):
            self.agent._write_session_report()


# BEHAVIOUR 5 — Réception des confirmations de commande depuis SupplierAgent
class ReceiveSupplierConfirmBehaviour(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return
        envelope = self.agent.parse_message(msg)
        if envelope is None:
            return
        d = envelope["payload"]
        logger.info(
            f"[INFO] ORDER {d.get('status')} | "
            f"ID={d.get('order_id')} | "
            f"{d.get('pharmacy_id')} | {d.get('drug_name')} | "
            f"Delivery={d.get('delivery_date', '?')} | "
            f"Qty={d.get('quantity', '?')} units"
        )

    async def on_start(self):
        logger.info("[INFO] DecisionAgent — ReceiveSupplierConfirmBehaviour STARTED.")

# BEHAVIOUR 6 — Réception des notifications de livraison depuis SupplierAgent
class ReceiveDeliveryBehaviour(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return
        envelope = self.agent.parse_message(msg)
        if envelope is None:
            return
        d = envelope["payload"]
        logger.info(
            f"[INFO] DELIVERY CONFIRMED | "
            f"ID={d.get('order_id')} | "
            f"{d.get('pharmacy_id')} | {d.get('drug_name')} | "
            f"Qty={d.get('quantity')} units added to stock."
        )
        _STATS["DELIVERIES_RECEIVED"] += 1

    async def on_start(self):
        logger.info("[INFO] DecisionAgent — ReceiveDeliveryBehaviour STARTED.")            

    # ── Rapport de session ────────────────────────────────────────────────────

    def _write_session_report(self) -> None:
        duration = round(time.time() - self._session_start, 1)
        report = {
            "duration_seconds": duration,
            "decisions":        dict(_STATS),
            "total_decisions":  sum(_STATS.values()),
            "ai_responses":     len(self._ai_responses),
            "forecasts_received": len(self._forecasts),
        }
        report_path = f"{RESULTS_DIR}decision_report.json"
        try:
            import os
            os.makedirs(RESULTS_DIR, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"[INFO] Session report saved → {report_path}")
        except Exception as e:
            logger.error(f"[ERROR] Could not save report: {e}")

        logger.info(
            f"[INFO] ══ DECISION AGENT SESSION REPORT ══ | "
            f"Duration={duration}s | "
            f"Total decisions={report['total_decisions']} | "
            f"AI calls={report['ai_responses']}"
        )
        for action, count in sorted(_STATS.items(), key=lambda x: -x[1]):
            logger.info(f"  {action:<40} : {count}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def setup(self):
        logger.info(f"[INFO] DecisionAgent online — JID: {self.jid}")

        # Template stock.alert
        t_stock = Template()
        t_stock.set_metadata("performative", "inform")
        t_stock.set_metadata("ontology", ONTOLOGY["STOCK_ALERT"])
        self.add_behaviour(self.HandleStockAlertBehavior(), t_stock)

        # Template prediction.response
        t_pred = Template()
        t_pred.set_metadata("performative", "inform")
        t_pred.set_metadata("ontology", ONTOLOGY["PREDICTION_RESPONSE"])
        self.add_behaviour(self.IntegrateForecastBehavior(), t_pred)

        # Template safety.alert
        t_safe = Template()
        t_safe.set_metadata("performative", "inform")
        t_safe.set_metadata("ontology", ONTOLOGY["SAFETY_ALERT"])
        self.add_behaviour(self.HandleSafetyAlertBehavior(), t_safe)

        # Template aiaas.response
        t_ai = Template()
        t_ai.set_metadata("performative", "inform")
        t_ai.set_metadata("ontology", ONTOLOGY["AIAAS_RESPONSE"])
        self.add_behaviour(self.ReceiveAIResponseBehavior(), t_ai)
        
         # Template — confirmations fournisseur
        t_confirm = Template()
        t_confirm.set_metadata("performative", "inform")
        t_confirm.set_metadata("ontology", ONTOLOGY["SUPPLIER_CONFIRM"])
        self.add_behaviour(self.ReceiveSupplierConfirmBehaviour(), t_confirm)
         # Template — livraisons fournisseur
        t_delivery = Template()
        t_delivery.set_metadata("performative", "inform")
        t_delivery.set_metadata("ontology", ONTOLOGY["SUPPLIER_DELIVERY"])
        self.add_behaviour(self.ReceiveDeliveryBehaviour(), t_delivery)
          