"""
test_niveau2_connexion.py
=========================
Rôle : Vérifier que chaque agent peut se connecter à Openfire
       AVANT de lancer le système complet (main.py).

Ce fichier fait 4 choses :
  1. Teste la connexion individuelle de chaque agent (7 agents maintenant)
  2. Vérifie que le port 5222 est accessible
  3. Mesure le temps de connexion de chaque agent
  4. Génère un rapport final clair

Usage :
    conda activate pfc_env
    cd C:\\Users\\X13\\pharma-mas-supplychain
    python test_niveau2_connexion.py
"""

import asyncio
import socket
import time
import sys

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour

# ─────────────────────────────────────────────────────────────
# CONFIGURATION — Modifie uniquement DOMAIN si nécessaire
# ─────────────────────────────────────────────────────────────
try:
    from config import AGENTS
    DOMAIN = list(AGENTS.values())[0]["jid"].split("@")[1]
    print(f"\n  [INFO] config.py trouvé — Domaine détecté : {DOMAIN}")
    COMPTES = [(v["jid"], v["password"], k) for k, v in AGENTS.items()]
except ImportError:
    print("\n  [INFO] config.py non trouvé — utilisation des valeurs par défaut")
    DOMAIN = "localhost"
    COMPTES = [
        ("pfc_stock_agent@localhost",          "StockAgent#Pfc2024!",     "stock"),
        ("pfc_prediction_agent@localhost",     "PredAgent#Pfc2024!",      "prediction"),
        ("pfc_decision_agent@localhost",       "DecisionAgent#Pfc2024!",  "decision"),
        ("pfc_safety_agent@localhost",         "SafetyAgent#Pfc2024!",    "safety"),
        ("pfc_aiaas_agent@localhost",          "AIaaSAgent#Pfc2024!",     "aiaas"),
        ("pfc_supplier_agent@localhost",       "SupplierAgent#Pfc2024!",  "supplier"),
        ("pfc_replenishment_agent@localhost",  "ReplenAgent#Pfc2024!",    "replenishment"), # 🎯 تم إضافة الوكيل السابع هنا
    ]

XMPP_PORT = 5222


# ─────────────────────────────────────────────────────────────
# CLASSE AGENT DE TEST
# ─────────────────────────────────────────────────────────────
class AgentDeTest(Agent):
    """
    Agent minimalist dont le seul rôle est de
    se connecter à Openfire et confirmer qu'il est vivant.
    Il ne fait rien d'autre — pas de comportements complexes.
    """
    class ConfirmerConnexion(OneShotBehaviour):
        async def run(self):
            # L'agent est connecté s'il peut exécuter ce behaviour
            self.agent.connexion_confirmee = True

    async def setup(self):
        self.connexion_confirmee = False
        self.add_behaviour(self.ConfirmerConnexion())


# ─────────────────────────────────────────────────────────────
# TEST 0 — Vérifier que le port 5222 est accessible
# ─────────────────────────────────────────────────────────────
def tester_port_openfire(domain: str, port: int) -> bool:
    print("\n" + "="*60)
    print("  PRÉ-TEST — Openfire accessible sur le réseau ?")
    print("="*60)
    try:
        s = socket.create_connection((domain, port), timeout=3)
        s.close()
        print(f"  ✅  Port {port} ouvert sur {domain} — Openfire répond")
        return True
    except socket.timeout:
        print(f"  ❌  Port {port} sur {domain} : TIMEOUT")
        print("      → Openfire est peut-être démarré mais surchargé")
        return False
    except ConnectionRefusedError:
        print(f"  ❌  Port {port} sur {domain} : CONNEXION REFUSÉE")
        print("      → Openfire n'est PAS démarré")
        print("      → Solution : Démarrer Openfire depuis Windows")
        return False
    except Exception as e:
        print(f"  ❌  Erreur inattendue : {e}")
        return False


# ─────────────────────────────────────────────────────────────
# TEST PRINCIPAL — Connexion de chaque agent
# ─────────────────────────────────────────────────────────────
async def tester_agent(jid: str, password: str, nom_cle: str) -> dict:
    """
    Tente de connecter un seul agent et retourne un rapport détaillé.
    """
    rapport = {
        "jid":          jid,
        "cle":          nom_cle,
        "connecte":     False,
        "temps_ms":     0,
        "erreur":       None,
    }

    
    agent = AgentDeTest(jid, password)
    debut = time.time()

    try:
        await agent.start()
        await asyncio.sleep(2)

        rapport["connecte"] = agent.is_alive()
        rapport["temps_ms"] = round((time.time() - debut) * 1000)

        await agent.stop()

    except Exception as e:
        rapport["erreur"]   = str(e)
        rapport["temps_ms"] = round((time.time() - debut) * 1000)

        # Diagnostic automatique de l'erreur
        err_str = str(e).lower()
        if "authentication" in err_str or "auth" in err_str:
            rapport["diagnostic"] = "Mot de passe incorrect ou compte inexistant dans Openfire"
        elif "connection" in err_str or "refused" in err_str:
            rapport["diagnostic"] = "Openfire non démarré ou port 5222 bloqué"
        elif "timeout" in err_str:
            rapport["diagnostic"] = "Openfire trop lent à répondre — réessayez"
        else:
            rapport["diagnostic"] = "Erreur inconnue — voir le détail ci-dessous"

    return rapport


async def lancer_tous_les_tests():
    # ── Pré-test : port Openfire ──────────────────────────────
    port_ok = tester_port_openfire(DOMAIN, XMPP_PORT)
    if not port_ok:
        print("\n  ARRÊT : Openfire inaccessible.")
        print("  Démarrez Openfire puis relancez ce script.")
        sys.exit(1)

    # ── Tests de connexion ────────────────────────────────────
    print("\n" + "="*60)
    print("  TEST NIVEAU 2 — Connexion individuelle des agents")
    print("="*60)
    print(f"  Domaine XMPP : {DOMAIN}:{XMPP_PORT}")
    print(f"  Agents à tester : {len(COMPTES)}")
    print()

    rapports = []
    for jid, password, cle in COMPTES:
        print(f"  Test en cours → {jid} ...", end="", flush=True)
        rapport = await tester_agent(jid, password, cle)
        rapports.append(rapport)

        if rapport["connecte"]:
            print(f"\r  ✅  [{cle:<12}]  {jid:<45}  ({rapport['temps_ms']} ms)")
        else:
            print(f"\r  ❌  [{cle:<12}]  {jid:<45}  ECHEC")
            if rapport["erreur"]:
                print(f"       Erreur     : {rapport['erreur'][:80]}")
            if "diagnostic" in rapport:
                print(f"       Diagnostic : {rapport['diagnostic']}")
                print(f"       Solution   : Vérifiez le compte dans Openfire Admin → Users")

        await asyncio.sleep(1)

    # ── Rapport final ─────────────────────────────────────────
    nb_ok    = sum(1 for r in rapports if r["connecte"])
    nb_total = len(rapports)
    temps_moy = round(
        sum(r["temps_ms"] for r in rapports if r["connecte"])
        / max(nb_ok, 1)
    )

    print()
    print("="*60)
    print("  RAPPORT FINAL")
    print("="*60)
    print(f"  Agents connectés   : {nb_ok}/{nb_total}")
    print(f"  Temps moyen        : {temps_moy} ms")
    print()

    if nb_ok == nb_total:
        print("  ✅  TOUS LES AGENTS SONT OPÉRATIONNELS")
        print()
        print("  Prochaines étapes :")
        print("    1. python test_niveau3_messages.py")
        print("    2. python main.py")
    else:
        agents_echec = [r["cle"] for r in rapports if not r["connecte"]]
        print(f"  ❌  AGENTS EN ÉCHEC : {agents_echec}")
        print()
        print("  Actions à faire :")
        print("    1. Ouvrir http://localhost:9090")
        print("    2. Users/Groups → Users → vérifier que le compte existe")
        print("    3. Si absent → Create New User avec les credentials de config.py")
        print("    4. Relancer ce script")

    print("="*60 + "\n")
    return nb_ok == nb_total


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    succes = asyncio.run(lancer_tous_les_tests())
    sys.exit(0 if succes else 1)