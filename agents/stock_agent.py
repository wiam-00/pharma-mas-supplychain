"""
agents/stock_agent.py
Agent de surveillance des stocks pharmaceutiques — PRODUCTEUR principal d'alertes.

Responsabilités :
  1. Lire les snapshots quotidiens depuis PharmacyEnvironment.
  2. Détecter les anomalies : rupture de stock (Stockout_Flag) et transferts urgents.
  3. Émettre des alertes JSON vers DecisionAgent (canal stock.alert).
  4. Émettre les données de demande vers PredictionAgent (canal prediction.request).
  5. Émettre les données d'expiry vers SafetyAgent (canal safety.check).

Communication :
  → DecisionAgent  : ontologie pharma.stock.alert
  → PredictionAgent: ontologie pharma.prediction.request
  → SafetyAgent    : ontologie pharma.safety.check
"""

import asyncio
import logging

from spade.behaviour import CyclicBehaviour

from agents.base_agent import BaseAgent
from simulation.env_simulator import PharmacyEnvironment
from config import ONTOLOGY, TICK_INTERVAL_SECONDS

logger = logging.getLogger("MAS.StockAgent")


class StockAgent(BaseAgent):

    AGENT_NAME = "StockAgent"

    def __init__(self, jid: str, password: str, environment: PharmacyEnvironment):
        super().__init__(jid, password)
        self.env = environment

    # ──────────────────────────────────────────────────────────────────────────
    class MonitorStockBehavior(CyclicBehaviour):
        """
        Comportement cyclique principal.
        1 itération = 1 snapshot quotidien (toutes pharmacies × tous drugs).
        """

        async def run(self):
            env = self.agent.env

            if not env.has_next():
                logger.info(
                    f"[INFO] StockAgent — Simulation complete "
                    f"({env.total_days} days processed). Stopping."
                )
                await self.agent.stop()
                return

            snapshot = env.next_snapshot()
            date_str = str(snapshot["Date"].iloc[0].date())

            # ── Canal 1 : Alertes stock → DecisionAgent ──────────────────────
            stock_alerts = env.get_stock_alerts(snapshot)
            if not stock_alerts.empty:
                for _, row in stock_alerts.iterrows():
                    await self.agent.send_message(
                        to_key="decision",
                        ontology=ONTOLOGY["STOCK_ALERT"],
                        payload=self._build_stock_alert(row),
                        behaviour=self,
                    )
                logger.warning(
                    f"[WARNING] {date_str} — {len(stock_alerts)} stock alert(s) sent "
                    f"to DecisionAgent."
                )
            else:
                logger.info(f"[INFO] {date_str} — No stock alerts.")

            # ── Canal 2 : Données demande → PredictionAgent ───────────────────
            demand_rows = env.get_demand_rows(snapshot)
            if not demand_rows.empty:
                # Envoi groupé par pharmacie × médicament (1 message = 1 série)
                for (ph_id, drug_id), group in demand_rows.groupby(
                    ["Pharmacy_ID", "Drug_ID"]
                ):
                    await self.agent.send_message(
                        to_key="prediction",
                        ontology=ONTOLOGY["PREDICTION_REQUEST"],
                        payload={
                            "date":        date_str,
                            "pharmacy_id": ph_id,
                            "drug_id":     drug_id,
                            "drug_name":   group["Drug_Name"].iloc[0],
                            "units_sold":  int(group["Units_Sold"].iloc[0]),
                            "stock_level": int(group["Stock_Level"].iloc[0]),
                            "max_capacity":int(group["Max_Capacity"].iloc[0]),
                        },
                        behaviour=self,
                    )

            # ── Canal 3 : Données péremption → SafetyAgent ───────────────────
            expiry_rows = env.get_expiry_rows(snapshot)
            if not expiry_rows.empty:
                for _, row in expiry_rows.iterrows():
                    await self.agent.send_message(
                        to_key="safety",
                        ontology=ONTOLOGY["SAFETY_CHECK"],
                        payload=self._build_expiry_payload(row),
                        behaviour=self,
                    )

            await asyncio.sleep(TICK_INTERVAL_SECONDS)

        # ── Builders de payload ───────────────────────────────────────────────

        @staticmethod
        def _build_stock_alert(row) -> dict:
            stock_pct = row["Stock_Level"] / max(row["Max_Capacity"], 1)
            return {
                "date":           str(row["Date"].date()),
                "pharmacy_id":    row["Pharmacy_ID"],
                "pharmacy_name":  row["Pharmacy_Name"],
                "city":           row["City"],
                "region":         row["Region"],
                "drug_id":        row["Drug_ID"],
                "drug_name":      row["Drug_Name"],
                "drug_category":  row["Drug_Category"],
                "units_sold":     int(row["Units_Sold"]),
                "stock_level":    int(row["Stock_Level"]),
                "stock_pct":      round(float(stock_pct), 4),
                "reorder_point":  int(row["Reorder_Point"]),
                "max_capacity":   int(row["Max_Capacity"]),
                "expiry_days":    int(row["Expiry_Days_Remaining"]),
                "is_critical":    int(row["Is_Critical_Drug"]),
                "stockout":       int(row["Stockout_Flag"]),
                "transfer_needed":int(row["Transfer_Needed_Flag"]),
                "near_expiry":    int(row["Near_Expiry_Flag"]),
                "unit_price":     float(row.get("Unit_Price_MAD", 0)),
            }

        @staticmethod
        def _build_expiry_payload(row) -> dict:
            return {
                "date":         str(row["Date"].date()),
                "pharmacy_id":  row["Pharmacy_ID"],
                "drug_id":      row["Drug_ID"],
                "drug_name":    row["Drug_Name"],
                "batch_id":     row.get("Batch_ID", "UNKNOWN"),
                "stock_level":  int(row["Stock_Level"]),
                "expiry_days":  int(row["Expiry_Days_Remaining"]),
                "expiry_date":  str(row["Expiry_Date"].date()),
                "is_critical":  int(row["Is_Critical_Drug"]),
                "unit_price":   float(row.get("Unit_Price_MAD", 0)),
            }

        async def on_start(self):
            logger.info("[INFO] StockAgent — MonitorStockBehavior STARTED.")

        async def on_end(self):
            logger.info("[INFO] StockAgent — MonitorStockBehavior ENDED.")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def setup(self):
        logger.info(f"[INFO] StockAgent online — JID: {self.jid}")
        self.add_behaviour(self.MonitorStockBehavior())