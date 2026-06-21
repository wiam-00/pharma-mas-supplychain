"""
config.py
Configuration centrale du projet MAS Pharma
"""

# ─────────────────────────────────────────────────────────────
# CONFIGURATION XMPP
# ─────────────────────────────────────────────────────────────

# IMPORTANT :
# Comme Openfire fonctionne en local,
# le domaine doit être localhost

XMPP_DOMAIN = "localhost"

AGENTS = {

    # ─── Agent de gestion de stock ──────────────────────────
    "stock": {
        "jid": f"pfc_stock_agent@{XMPP_DOMAIN}",
        "password": "StockAgent#Pfc2024!",
    },

    # ─── Agent de prédiction IA ─────────────────────────────
    "prediction": {
        "jid": f"pfc_prediction_agent@{XMPP_DOMAIN}",
        "password": "PredAgent#Pfc2024!",
    },

    # ─── Agent de décision ──────────────────────────────────
    "decision": {
        "jid": f"pfc_decision_agent@{XMPP_DOMAIN}",
        "password": "DecisionAgent#Pfc2024!",
    },

    # ─── Agent de sécurité pharmaceutique ───────────────────
    "safety": {
        "jid": f"pfc_safety_agent@{XMPP_DOMAIN}",
        "password": "SafetyAgent#Pfc2024!",
    },

    # ─── Agent AIaaS ────────────────────────────────────────
    "aiaas": {
        "jid": f"pfc_aiaas_agent@{XMPP_DOMAIN}",
        "password": "AIaaSAgent#Pfc2024!",
    },
     # --- Agent fournisseur ---
    "supplier":   {
        "jid": "pfc_supplier_agent@localhost",  
          "password": "SupplierAgent#Pfc2024!"
    },
    # --- Agent de réapprovisionnement  ---
    "replenishment": {
        "jid": "pfc_replenishment_agent@localhost",  
         "password": "ReplenishmentAgent#Pfc2024!"
}

    

}


# ─────────────────────────────────────────────────────────────
# ONTOLOGIES DE COMMUNICATION
# ─────────────────────────────────────────────────────────────

ONTOLOGY = {

    # Alertes stock
    "STOCK_ALERT": "pharma.stock.alert",

    # Prédiction IA
    "PREDICTION_REQUEST": "pharma.prediction.request",
    "PREDICTION_RESPONSE": "pharma.prediction.response",

    # Sécurité
    "SAFETY_CHECK": "pharma.safety.check",
    "SAFETY_ALERT": "pharma.safety.alert",

    # AIaaS
    "AIAAS_REQUEST": "pharma.aiaas.request",
    "AIAAS_RESPONSE": "pharma.aiaas.response",
    "SUPPLIER_ORDER":    "pharma.supplier.order",    # DecisionAgent → SupplierAgent
    "SUPPLIER_CONFIRM":  "pharma.supplier.confirm",  # SupplierAgent → DecisionAgent
    "SUPPLIER_DELIVERY": "pharma.supplier.delivery", # SupplierAgent → DecisionAgent + StockAgent
}

# ─────────────────────────────────────────────────────────────
# DATASETS ET DOSSIERS
# ─────────────────────────────────────────────────────────────

DATASET_PATH = "data/pharma_mas_dataset.csv"

DATASET_PATH_RAW = "data/pharma_mas_dataset.csv"

AI_MODELS_DIR = "ai_models/"

RESULTS_DIR = "results/"

# ─────────────────────────────────────────────────────────────
# PARAMÈTRES DE SIMULATION
# ─────────────────────────────────────────────────────────────

# Délai entre snapshots
TICK_INTERVAL_SECONDS = 1

# Temps d’attente au démarrage des agents
STARTUP_DELAY_SECONDS = 3

# Dates de simulation
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"

# ─────────────────────────────────────────────────────────────
# SEUILS DE DÉCISION
# ─────────────────────────────────────────────────────────────

# Médicament proche expiration
NEAR_EXPIRY_THRESHOLD_DAYS = 30

# Stock critique
LOW_STOCK_PCT = 0.20

# Stock urgence absolue
CRITICAL_LOW_STOCK_PCT = 0.05

# Horizon de prédiction
FORECAST_HORIZON_DAYS = 7

# ─────────────────────────────────────────────────────────────
# CONFIGURATION AIaaS / ANTHROPIC
# ─────────────────────────────────────────────────────────────

# Laisser vide pour mode simulation
ANTHROPIC_API_KEY = ""

# Modèle Claude
AIAAS_MODEL = "claude-sonnet-4-20250514"

# Nombre maximal de tokens
AIAAS_MAX_TOKENS = 512

# True = simulation locale
# False = appel API réel
AIAAS_SIMULATE_MODE = True

# ─────────────────────────────────────────────────────────────
# CONFIGURATION OPENFIRE
# ─────────────────────────────────────────────────────────────

OPENFIRE_HOST = "localhost"

# Port client XMPP standard
OPENFIRE_PORT = 5222

# Interface admin Openfire
OPENFIRE_ADMIN_URL = "http://localhost:9090"

# ─────────────────────────────────────────────────────────────
# DEBUG / LOGS
# ─────────────────────────────────────────────────────────────

DEBUG = True

LOG_LEVEL = "INFO"