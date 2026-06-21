"""
agents/supplier_agent.py
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from collections import defaultdict

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.template import Template

from agents.base_agent import BaseAgent
from config import ONTOLOGY

logger = logging.getLogger("MAS.SupplierAgent")

# ── Ontologies supplémentaires à ajouter dans config.py ──────────────────────
# "SUPPLIER_ORDER":    "pharma.supplier.order"
# "SUPPLIER_CONFIRM":  "pharma.supplier.confirm"
# "SUPPLIER_DELIVERY": "pharma.supplier.delivery"

LEAD_TIME_BY_CATEGORY = {
    "Urgence":          1,
    "Antibiotique":     3,
    "Antalgique":       2,
    "Anti-inflam.":     2,
    "Cardio.":          3,
    "Antidiabétique":   3,
    "Antihistaminique": 2,
    "Supplément":       2,
    "Vaccin":           7,
    "Gastro.":          2,
    "Dermatologie":     3,
    "Antidépresseur":   4,
    "Anxiolytique":     4,
}

ORDER_STATUS = {
    "PENDING":    "Order received, awaiting processing.",
    "CONFIRMED":  "Order confirmed by supplier.",
    "SHIPPED":    "Order shipped to pharmacy.",
    "DELIVERED":  "Order delivered successfully.",
    "CANCELLED":  "Order cancelled.",
}


class SupplierAgent(BaseAgent):

    AGENT_NAME = "SupplierAgent"

    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)
        # order_id → order dict
        self._orders: dict = {}
        # pharmacy_id → list of pending order_ids
        self._pending_by_pharmacy: dict = defaultdict(list)
        self._stats = defaultdict(int)

    # ─────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 1 — Réception des ordres de commande depuis DecisionAgent
    # ─────────────────────────────────────────────────────────────────────────
    class ReceiveOrderBehaviour(CyclicBehaviour):

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            data        = envelope["payload"]
            order_id    = data.get("order_id", f"ORD_{uuid.uuid4().hex[:8].upper()}")
            pharmacy_id = data.get("pharmacy_id", "UNKNOWN")
            drug_id     = data.get("drug_id",     "UNKNOWN")
            drug_name   = data.get("drug_name",   "UNKNOWN")
            drug_cat    = data.get("drug_category", "")
            qty         = int(data.get("quantity_ordered", 0))
            urgency     = data.get("urgency", "STANDARD")   # EXPRESS | STANDARD
            unit_price  = float(data.get("unit_price", 0.0))
            date_str    = data.get("date", str(datetime.now().date()))

            lead_time = (
                1 if urgency == "EXPRESS"
                else LEAD_TIME_BY_CATEGORY.get(drug_cat, 3)
            )
            delivery_date = (
                datetime.now() + timedelta(days=lead_time)
            ).strftime("%Y-%m-%d")
            total_cost = round(qty * unit_price, 2)

            order = {
                "order_id":      order_id,
                "pharmacy_id":   pharmacy_id,
                "drug_id":       drug_id,
                "drug_name":     drug_name,
                "drug_category": drug_cat,
                "quantity":      qty,
                "urgency":       urgency,
                "unit_price":    unit_price,
                "total_cost_mad":total_cost,
                "lead_time_days":lead_time,
                "delivery_date": delivery_date,
                "status":        "CONFIRMED",
                "created_at":    date_str,
            }

            self.agent._orders[order_id] = order
            self.agent._pending_by_pharmacy[pharmacy_id].append(order_id)
            self.agent._stats["orders_received"] += 1
            self.agent._stats["total_units_ordered"] += qty

            log_fn = logger.critical if urgency == "EXPRESS" else logger.warning
            log_fn(
                f"[ORDER {urgency}] SupplierAgent — "
                f"ID={order_id} | {pharmacy_id} | {drug_name} | "
                f"Qty={qty} units | Cost={total_cost:.0f} MAD | "
                f"Delivery={delivery_date} ({lead_time}d)"
            )

            # ── Envoyer confirmation à DecisionAgent ─────────────────────────
            await self.agent.send_message(
                to_key="decision",
                ontology=ONTOLOGY.get("SUPPLIER_CONFIRM", "pharma.supplier.confirm"),
                payload={
                    "order_id":      order_id,
                    "pharmacy_id":   pharmacy_id,
                    "drug_id":       drug_id,
                    "drug_name":     drug_name,
                    "quantity":      qty,
                    "status":        "CONFIRMED",
                    "delivery_date": delivery_date,
                    "lead_time_days":lead_time,
                    "total_cost_mad":total_cost,
                    "urgency":       urgency,
                    "date":          date_str,
                },
                behaviour=self,
            )

        async def on_start(self):
            logger.info("[INFO] SupplierAgent — ReceiveOrderBehaviour STARTED.")

        async def on_end(self):
            logger.info("[INFO] SupplierAgent — ReceiveOrderBehaviour ENDED.")

    # ─────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 2 — Simulation des livraisons (toutes les 30 secondes)
    #               Fait passer les commandes CONFIRMED → DELIVERED
    #               et notifie DecisionAgent + StockAgent
    # ─────────────────────────────────────────────────────────────────────────
    class ProcessDeliveryBehaviour(PeriodicBehaviour):

        async def run(self):
            today = datetime.now().strftime("%Y-%m-%d")
            delivered = []

            for order_id, order in list(self.agent._orders.items()):
                if (
                    order["status"] == "CONFIRMED"
                    and order["delivery_date"] <= today
                ):
                    order["status"] = "DELIVERED"
                    delivered.append(order)
                    self.agent._stats["orders_delivered"] += 1

                    logger.info(
                        f"[DELIVERY] SupplierAgent — "
                        f"ID={order_id} | {order['pharmacy_id']} | "
                        f"{order['drug_name']} | "
                        f"Qty={order['quantity']} units DELIVERED."
                    )

                    # ── Notifier DecisionAgent de la livraison ────────────────
                    await self.agent.send_message(
                        to_key="decision",
                        ontology=ONTOLOGY.get(
                            "SUPPLIER_DELIVERY", "pharma.supplier.delivery"
                        ),
                        payload={
                            "order_id":    order_id,
                            "pharmacy_id": order["pharmacy_id"],
                            "drug_id":     order["drug_id"],
                            "drug_name":   order["drug_name"],
                            "quantity":    order["quantity"],
                            "status":      "DELIVERED",
                            "date":        today,
                        },
                        behaviour=self,
                    )

                    # ── Notifier StockAgent pour mise à jour du stock ─────────
                    await self.agent.send_message(
                        to_key="stock",
                        ontology=ONTOLOGY.get(
                            "SUPPLIER_DELIVERY", "pharma.supplier.delivery"
                        ),
                        payload={
                            "order_id":         order_id,
                            "pharmacy_id":      order["pharmacy_id"],
                            "drug_id":          order["drug_id"],
                            "drug_name":        order["drug_name"],
                            "quantity_received":order["quantity"],
                            "status":           "DELIVERED",
                            "date":             today,
                        },
                        behaviour=self,
                    )

            if delivered:
                logger.info(
                    f"[INFO] SupplierAgent — {len(delivered)} delivery(ies) "
                    f"processed today ({today})."
                )

        async def on_start(self):
            logger.info(
                "[INFO] SupplierAgent — ProcessDeliveryBehaviour STARTED "
                "(checking deliveries every 30s)."
            )

        async def on_end(self):
            self.agent._write_session_report()

    # ─────────────────────────────────────────────────────────────────────────
    # BEHAVIOUR 3 — Gestion des annulations depuis DecisionAgent
    # ─────────────────────────────────────────────────────────────────────────
    class HandleCancellationBehaviour(CyclicBehaviour):

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            data     = envelope["payload"]
            order_id = data.get("order_id")

            if order_id not in self.agent._orders:
                logger.warning(
                    f"[WARNING] SupplierAgent — "
                    f"Cancellation received for unknown order: {order_id}"
                )
                return

            order = self.agent._orders[order_id]

            if order["status"] in ("DELIVERED", "CANCELLED"):
                logger.warning(
                    f"[WARNING] SupplierAgent — "
                    f"Cannot cancel order {order_id} "
                    f"(status={order['status']})."
                )
                return

            order["status"] = "CANCELLED"
            self.agent._stats["orders_cancelled"] += 1

            logger.warning(
                f"[WARNING] SupplierAgent — "
                f"Order CANCELLED | ID={order_id} | "
                f"{order['pharmacy_id']} | {order['drug_name']}"
            )

            await self.agent.send_message(
                to_key="decision",
                ontology=ONTOLOGY.get("SUPPLIER_CONFIRM", "pharma.supplier.confirm"),
                payload={
                    "order_id":    order_id,
                    "pharmacy_id": order["pharmacy_id"],
                    "drug_name":   order["drug_name"],
                    "status":      "CANCELLED",
                    "date":        str(datetime.now().date()),
                },
                behaviour=self,
            )

        async def on_start(self):
            logger.info(
                "[INFO] SupplierAgent — HandleCancellationBehaviour STARTED."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION REPORT
    # ─────────────────────────────────────────────────────────────────────────
    def _write_session_report(self):
        total_cost = sum(
            o["total_cost_mad"]
            for o in self._orders.values()
        )
        pending = sum(
            1 for o in self._orders.values()
            if o["status"] == "CONFIRMED"
        )
        logger.info(
            f"[INFO] SupplierAgent — SESSION REPORT | "
            f"Received={self._stats['orders_received']} | "
            f"Delivered={self._stats['orders_delivered']} | "
            f"Cancelled={self._stats['orders_cancelled']} | "
            f"Pending={pending} | "
            f"Total units={self._stats['total_units_ordered']} | "
            f"Total cost={total_cost:,.0f} MAD"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────
    async def setup(self):
        logger.info(f"[INFO] SupplierAgent online — JID: {self.jid}")

        # Template — réception des ordres de commande
        t_order = Template()
        t_order.set_metadata("performative", "request")
        t_order.set_metadata(
            "ontology",
            ONTOLOGY.get("SUPPLIER_ORDER", "pharma.supplier.order")
        )
        self.add_behaviour(self.ReceiveOrderBehaviour(), t_order)

        # Livraisons périodiques — toutes les 30 secondes
        self.add_behaviour(
            self.ProcessDeliveryBehaviour(period=30)
        )

        # Template — annulations
        t_cancel = Template()
        t_cancel.set_metadata("performative", "cancel")
        t_cancel.set_metadata(
            "ontology",
            ONTOLOGY.get("SUPPLIER_ORDER", "pharma.supplier.order")
        )
        self.add_behaviour(self.HandleCancellationBehaviour(), t_cancel)