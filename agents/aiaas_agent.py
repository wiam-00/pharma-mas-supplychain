"""
agents/aiaas_agent.py
Agent AI-as-a-Service — Raisonnement intelligent via Claude (Anthropic API).

Responsabilités :
  1. Recevoir des requêtes de raisonnement complexe depuis DecisionAgent.
  2. Construire un prompt structuré avec le contexte de la situation.
  3. Interroger l'API Anthropic (ou simuler la réponse si mode SIMULATE).
  4. Retourner une recommandation structurée en JSON à DecisionAgent.

Mode SIMULATE (par défaut, AIAAS_SIMULATE_MODE=True dans config.py) :
  L'agent construit une recommandation déterministe basée sur des règles métier,
  sans appel API réel. Permet de travailler sans clé API.

Mode REAL (AIAAS_SIMULATE_MODE=False + ANTHROPIC_API_KEY renseignée) :
  Appel réel à claude-sonnet-4-20250514 via l'endpoint /v1/messages.

Communication :
  ← DecisionAgent : ontologie pharma.aiaas.request
  → DecisionAgent : ontologie pharma.aiaas.response
"""

import asyncio
import json
import logging

import aiohttp
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from agents.base_agent import BaseAgent
from config import (
    ONTOLOGY,
    ANTHROPIC_API_KEY,
    AIAAS_MODEL,
    AIAAS_MAX_TOKENS,
    AIAAS_SIMULATE_MODE,
)

logger = logging.getLogger("MAS.AIaaSAgent")

_SYSTEM_PROMPT = """You are an expert pharmaceutical supply chain AI assistant.
You analyze stock shortage situations and provide structured logistics recommendations.
Always respond ONLY with a valid JSON object — no markdown, no preamble.
JSON schema:
{
  "decision": "EMERGENCY_TRANSFER | SUPPLIER_ORDER_EXPRESS | SUPPLIER_ORDER_STANDARD | WASTE_PREVENTION | MONITOR",
  "confidence": 0.0-1.0,
  "justification": "one sentence",
  "recommended_qty": integer,
  "urgency_hours": integer,
  "alternative_pharmacy": "PH_ID or null"
}"""


def _simulate_recommendation(context: dict) -> dict:
    """
    Règles déterministes pour simuler une réponse IA sans API.
    Reproduit la logique d'un LLM bien prompt sur ce domaine.
    """
    stockout     = context.get("stockout", 0)
    is_critical  = context.get("is_critical", 0)
    stock_pct    = context.get("stock_pct", 1.0)
    expiry_days  = context.get("expiry_days", 999)
    forecast_avg = context.get("forecast_avg_daily", 0)
    max_cap      = context.get("max_capacity", 100)

    if stockout and is_critical:
        return {
            "decision":             "EMERGENCY_TRANSFER",
            "confidence":           0.95,
            "justification":        "Critical drug stockout detected — inter-pharmacy emergency transfer required.",
            "recommended_qty":      int(max_cap * 0.5),
            "urgency_hours":        4,
            "alternative_pharmacy": "PH010",
        }
    elif stock_pct < 0.10 and is_critical:
        qty = max(int(forecast_avg * 7), 10)
        return {
            "decision":             "SUPPLIER_ORDER_EXPRESS",
            "confidence":           0.88,
            "justification":        "Critical stock below 10% — express supplier order needed within 24h.",
            "recommended_qty":      qty,
            "urgency_hours":        24,
            "alternative_pharmacy": None,
        }
    elif expiry_days <= 7:
        return {
            "decision":             "WASTE_PREVENTION",
            "confidence":           0.91,
            "justification":        "Batch expiring within 7 days — immediate redistribution to high-demand pharmacies.",
            "recommended_qty":      context.get("stock_level", 0),
            "urgency_hours":        12,
            "alternative_pharmacy": None,
        }
    elif stock_pct < 0.20:
        qty = int(max_cap * 0.80)
        return {
            "decision":             "SUPPLIER_ORDER_STANDARD",
            "confidence":           0.75,
            "justification":        "Stock below reorder threshold — standard replenishment order recommended.",
            "recommended_qty":      qty,
            "urgency_hours":        72,
            "alternative_pharmacy": None,
        }
    else:
        return {
            "decision":             "MONITOR",
            "confidence":           0.60,
            "justification":        "Stock levels acceptable — continue monitoring.",
            "recommended_qty":      0,
            "urgency_hours":        168,
            "alternative_pharmacy": None,
        }


async def _call_anthropic_api(context: dict) -> dict:
    """
    Appel réel à l'API Anthropic /v1/messages.
    Uniquement utilisé si AIAAS_SIMULATE_MODE=False et ANTHROPIC_API_KEY renseignée.
    """
    user_prompt = (
        f"Analyze this pharmaceutical stock situation and provide a recommendation:\n"
        f"{json.dumps(context, indent=2, default=str)}"
    )
    body = {
        "model":      AIAAS_MODEL,
        "max_tokens": AIAAS_MAX_TOKENS,
        "system":     _SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Anthropic API error {resp.status}: {text[:200]}")
            data = await resp.json()

    raw_text = data["content"][0]["text"].strip()
    # Strip possible markdown fences
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    return json.loads(raw_text)


class AIaaSAgent(BaseAgent):

    AGENT_NAME = "AIaaSAgent"

    # ──────────────────────────────────────────────────────────────────────────
    class AIReasoningBehavior(CyclicBehaviour):
        """Reçoit les requêtes de raisonnement et renvoie une recommandation IA."""

        async def run(self):
            msg = await self.receive(timeout=15)
            if msg is None:
                return

            envelope = self.agent.parse_message(msg)
            if envelope is None:
                return

            context      = envelope["payload"]
            request_id   = context.get("request_id", "REQ_?")
            pharmacy_id  = context.get("pharmacy_id", "?")
            drug_name    = context.get("drug_name", "?")

            logger.info(
                f"[INFO] AIaaSAgent — Processing {request_id} | "
                f"{pharmacy_id} | {drug_name} | "
                f"Mode={'SIMULATE' if AIAAS_SIMULATE_MODE else 'REAL_API'}"
            )

            # ── Appel IA (simulé ou réel) ──────────────────────────────────
            try:
                if AIAAS_SIMULATE_MODE or not ANTHROPIC_API_KEY:
                    recommendation = _simulate_recommendation(context)
                    source = "SIMULATE"
                else:
                    recommendation = await _call_anthropic_api(context)
                    source = "CLAUDE_API"
            except Exception as e:
                logger.error(f"[ERROR] AIaaSAgent — API call failed: {e}. Falling back to SIMULATE.")
                recommendation = _simulate_recommendation(context)
                source = "SIMULATE_FALLBACK"

            # ── Envoi de la réponse à DecisionAgent ────────────────────────
            await self.agent.send_message(
                to_key="decision",
                ontology=ONTOLOGY["AIAAS_RESPONSE"],
                payload={
                    "request_id":    request_id,
                    "pharmacy_id":   pharmacy_id,
                    "drug_name":     drug_name,
                    "date":          context.get("date", "?"),
                    "recommendation":recommendation,
                    "source":        source,
                },
                behaviour=self,
            )

            logger.info(
                f"[INFO] AIaaSAgent → DecisionAgent | "
                f"Decision={recommendation['decision']} | "
                f"Confidence={recommendation['confidence']:.0%} | "
                f"Source={source}"
            )

        async def on_start(self):
            logger.info(
                f"[INFO] AIaaSAgent — AIReasoningBehavior STARTED "
                f"(mode={'SIMULATE' if AIAAS_SIMULATE_MODE else 'REAL_API'})."
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def setup(self):
        logger.info(f"[INFO] AIaaSAgent online — JID: {self.jid}")
        template = Template()
        template.set_metadata("performative", "request")
        template.set_metadata("ontology",     ONTOLOGY["AIAAS_REQUEST"])
        self.add_behaviour(self.AIReasoningBehavior(), template)