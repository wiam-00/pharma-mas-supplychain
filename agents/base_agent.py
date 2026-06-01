"""
agents/base_agent.py
Classe mère abstraite pour tous les agents du MAS Pharma Supply Chain.

Rôle :
  - Fournit les méthodes utilitaires de communication XMPP (send_message,
    build_message) partagées par tous les agents enfants.
  - Standardise le format des messages JSON (enveloppe + payload).
  - Centralise la configuration du logger par agent.
  - Expose get_peer_jid() pour résoudre les JID cibles sans import circulaire.

Utilisation (dans un agent enfant) :
    class StockAgent(BaseAgent):
        async def setup(self):
            await self.send_message(
                to_key="decision",
                ontology=ONTOLOGY["STOCK_ALERT"],
                payload={"drug": "Amox", "stock": 0}
            )
"""

import json
import logging
import time
from abc import ABC

from spade.agent import Agent
from spade.message import Message

from config import AGENTS, ONTOLOGY


def _get_agent_logger(agent_name: str) -> logging.Logger:
    """Retourne un logger nommé au format 'MAS.<AgentName>'."""
    return logging.getLogger(f"MAS.{agent_name}")


class BaseAgent(Agent, ABC):
    """
    Classe mère abstraite. Tous les agents héritent de cette classe.
    Ne pas instancier directement.
    """

    # Sous-classes DOIVENT définir ce nom (utilisé pour les logs)
    AGENT_NAME: str = "BaseAgent"

    def __init__(self, jid: str, password: str):
        super().__init__(jid, password, auto_register=True)
        self.log = _get_agent_logger(self.AGENT_NAME)

    # ──────────────────────────────────────────────────────────────────────────
    # COMMUNICATION HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def get_peer_jid(self, agent_key: str) -> str:
        """
        Résout le JID d'un agent cible via sa clé dans config.AGENTS.
        Exemple : self.get_peer_jid("decision") → "pfc_decision_agent@xmpp.jp"
        """
        if agent_key not in AGENTS:
            raise KeyError(
                f"[{self.AGENT_NAME}] Unknown agent key '{agent_key}'. "
                f"Valid keys: {list(AGENTS.keys())}"
            )
        return AGENTS[agent_key]["jid"]

    def build_message(
        self,
        to_jid: str,
        ontology: str,
        payload: dict,
        performative: str = "inform",
    ) -> Message:
        """
        Construit un objet Message XMPP standardisé avec :
          - metadata performative  (ex: "inform", "request", "agree")
          - metadata ontology      (ex: "pharma.stock.alert")
          - body                   JSON sérialisé du payload + enveloppe horodatée

        L'enveloppe standardisée ajoute automatiquement :
          - sender    : AGENT_NAME de l'émetteur
          - timestamp : epoch UNIX (float)
        """
        envelope = {
            "sender":    self.AGENT_NAME,
            "timestamp": time.time(),
            "payload":   payload,
        }
        msg = Message(to=to_jid)
        msg.set_metadata("performative", performative)
        msg.set_metadata("ontology",     ontology)
        msg.body = json.dumps(envelope, ensure_ascii=False, default=str)
        return msg

    async def send_message(
        self,
        to_key: str,
        ontology: str,
        payload: dict,
        performative: str = "inform",
        behaviour=None,
    ) -> None:
        """
        Méthode principale d'envoi de message inter-agents.

        Args:
            to_key      : Clé de l'agent cible dans config.AGENTS
                          (ex: "decision", "prediction", "aiaas")
            ontology    : Chaîne d'ontologie XMPP depuis config.ONTOLOGY
            payload     : Dictionnaire de données à envoyer
            performative: Performatif FIPA (défaut: "inform")
            behaviour   : Behaviour appelant (pour utiliser behaviour.send).
                          Si None, utilise self.send (moins courant avec SPADE v4).
        """
        to_jid = self.get_peer_jid(to_key)
        msg    = self.build_message(to_jid, ontology, payload, performative)

        if behaviour is not None:
            await behaviour.send(msg)
        else:
            raise RuntimeError(
                f"[{self.AGENT_NAME}] send_message() doit être appelé depuis "
                f"un Behaviour. Passez 'behaviour=self' depuis le comportement."
            )

        self.log.debug(
            f"[SEND] → {to_key} | ontology={ontology} | "
            f"payload_keys={list(payload.keys())}"
        )

    @staticmethod
    def parse_message(msg: Message) -> dict | None:
        """
        Désérialise le body d'un message XMPP reçu.
        Retourne l'enveloppe complète (sender, timestamp, payload)
        ou None en cas d'erreur de parsing.
        """
        try:
            return json.loads(msg.body)
        except (json.JSONDecodeError, AttributeError) as e:
            logging.getLogger("MAS.BaseAgent").error(
                f"[PARSE ERROR] Cannot deserialize message body: {e} | "
                f"raw='{msg.body[:80] if msg.body else 'None'}'"
            )
            return None