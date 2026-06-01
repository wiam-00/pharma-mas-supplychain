"""
main.py — Point d'entrée du Système Multi-Agents Pharma Supply Chain.

Ordre de démarrage (critique pour XMPP) :
  1. AIaaSAgent     — doit écouter avant que DecisionAgent délègue
  2. PredictionAgent — doit écouter avant que StockAgent envoie
  3. SafetyAgent     — idem
  4. DecisionAgent   — doit écouter avant que StockAgent envoie des alertes
  5. StockAgent      — lance la simulation (producteur)

Usage :
    conda activate pfc_env
    cd pharma-mas-supplychain
    python main.py
"""

import asyncio
import logging
import os
import sys

from agents.stock_agent      import StockAgent
from agents.prediction_agent import PredictionAgent
from agents.decision_agent   import DecisionAgent
from agents.safety_agent     import SafetyAgent
from agents.aiaas_agent      import AIaaSAgent
from simulation.env_simulator import PharmacyEnvironment
from config import AGENTS, STARTUP_DELAY_SECONDS, RESULTS_DIR

# ─── LOGGING ──────────────────────────────────────────────────────────────────
os.makedirs(RESULTS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"{RESULTS_DIR}mas_simulation.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("MAS.Main")


async def main() -> None:
    logger.info("=" * 72)
    logger.info(" PHARMA MAS SUPPLY CHAIN — SYSTEM STARTUP")
    logger.info("=" * 72)

    # ── 1. Environnement ──────────────────────────────────────────────────────
    env = PharmacyEnvironment()
    logger.info(f"[INFO] Simulation: {env.total_days} days to process.")

    # ── 2. Instanciation des agents ───────────────────────────────────────────
    aiaas_agent  = AIaaSAgent(
        jid=AGENTS["aiaas"]["jid"],
        password=AGENTS["aiaas"]["password"],
    )
    pred_agent   = PredictionAgent(
        jid=AGENTS["prediction"]["jid"],
        password=AGENTS["prediction"]["password"],
    )
    safety_agent = SafetyAgent(
        jid=AGENTS["safety"]["jid"],
        password=AGENTS["safety"]["password"],
    )
    decision_agent = DecisionAgent(
        jid=AGENTS["decision"]["jid"],
        password=AGENTS["decision"]["password"],
    )
    stock_agent  = StockAgent(
        jid=AGENTS["stock"]["jid"],
        password=AGENTS["stock"]["password"],
        environment=env,
    )

    # ── 3. Démarrage séquentiel (consommateurs d'abord) ───────────────────────
    logger.info("[INFO] Starting consumer agents...")
    await aiaas_agent.start(auto_register=True)
    await asyncio.sleep(1)
    await pred_agent.start(auto_register=True)
    await asyncio.sleep(1)
    await safety_agent.start(auto_register=True)
    await asyncio.sleep(1)
    await decision_agent.start(auto_register=True)

    logger.info(
        f"[INFO] All consumer agents online. "
        f"Waiting {STARTUP_DELAY_SECONDS}s before launching StockAgent..."
    )
    await asyncio.sleep(STARTUP_DELAY_SECONDS)

    # ── 4. Lancement du producteur (StockAgent = moteur de simulation) ────────
    logger.info("[INFO] Starting StockAgent — simulation begins NOW.")
    await stock_agent.start(auto_register=True)

    logger.info("[INFO] All 5 agents are online. Press Ctrl+C to interrupt.")

    # ── 5. Boucle d'attente ───────────────────────────────────────────────────
    try:
        while stock_agent.is_alive():
            if env.total_days > 0:
                pct = env.progress_pct
                if int(pct) % 10 == 0:
                    logger.info(f"[INFO] Simulation progress: {pct:.1f}%")
            await asyncio.sleep(5)
    except KeyboardInterrupt:
        logger.info("[INFO] KeyboardInterrupt — graceful shutdown initiated.")

    # ── 6. Arrêt propre ───────────────────────────────────────────────────────
    logger.info("[INFO] Stopping all agents...")
    for agent in [stock_agent, decision_agent, safety_agent, pred_agent, aiaas_agent]:
        if agent.is_alive():
            await agent.stop()

    logger.info("=" * 72)
    logger.info(" PHARMA MAS — SIMULATION COMPLETE")
    logger.info(f" Logs saved to: {RESULTS_DIR}mas_simulation.log")
    logger.info(f" Report saved to: {RESULTS_DIR}decision_report.json")
    logger.info("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())