import json
import asyncio

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

import config


class ReplenishmentAgent(Agent):

    class ListenRiskBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg:
                try:
                    data = json.loads(msg.body)
                except (json.JSONDecodeError, TypeError):
                    return

                if data.get("status") == "RISQUE_RUPTURE":
                    stock_actuel = data.get("stock_actuel", 0)
                    quantite = 100 - stock_actuel

                    print(f"[ReplenishmentAgent] RISQUE_RUPTURE détecté. "
                          f"Stock actuel: {stock_actuel} -> Quantité à commander: {quantite}")

                    commande = Message(to=config.AGENT_SUPPLIER_JID)
                    commande.set_metadata("performative", "request")
                    commande.body = json.dumps({
                        "action": "PASSER_COMMANDE",
                        "quantite": quantite
                    })

                    await self.send(commande)
                    print(f"[ReplenishmentAgent] Commande envoyée à {config.AGENT_SUPPLIER_JID} "
                          f"pour {quantite} unités.")

    class ListenSupplierConfirmationBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg:
                try:
                    data = json.loads(msg.body)
                except (json.JSONDecodeError, TypeError):
                    return

                if data.get("status") == "CONFIRME":
                    print(f"[ReplenishmentAgent] Confirmation du fournisseur reçue : {data}")

    async def setup(self):
        print(f"[ReplenishmentAgent] Agent démarré avec JID : {str(self.jid)}")

        risk_template = Template()
        risk_template.set_metadata("performative", "inform")

        confirm_template = Template()
        confirm_template.set_metadata("performative", "confirm")

        self.add_behaviour(self.ListenRiskBehaviour(), risk_template)
        self.add_behaviour(self.ListenSupplierConfirmationBehaviour(), confirm_template)


if __name__ == "__main__":
    replenishment_agent = ReplenishmentAgent(
        config.AGENT_REPLENISHMENT_JID,
        config.AGENT_REPLENISHMENT_PASSWORD
    )

    async def main():
        await replenishment_agent.start(auto_register=True)
        print("ReplenishmentAgent en cours d'exécution. CTRL+C pour arrêter.")
        while replenishment_agent.is_alive():
            try:
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                await replenishment_agent.stop()
                break

    asyncio.run(main())