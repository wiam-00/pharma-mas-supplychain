"""
config.py
Centralise tous les paramètres du projet MAS Pharma.
Ne jamais committer ce fichier avec de vraies credentials — ajoutez-le au .gitignore
ou utilisez python-dotenv pour les environnements de production.
"""

# ─── XMPP ────────────────────────────────────────────────────────────────────
XMPP_DOMAIN = "xmpp.jp"

AGENTS = {
    "stock": {
        "jid":      f"pfc_stock_agent@xmpp.jp",
        "password": "StockAgent#Pfc2024!",
    },
    "prediction": {
        "jid":      f"pfc_prediction_agent@xmpp.jp",
        "password": "PredAgent#Pfc2024!",
    },
    "decision": {
        "jid":      f"pfc_decision_agent@xmpp.jp",
        "password": "DecisionAgent#Pfc2024!",
    },
    "safety": {
        "jid":      f"pfc_safety_agent@xmpp.jp",
        "password": "SafetyAgent#Pfc2024!",
    },
    "aiaas": {
        "jid":      f"pfc_aiaas_agent@xmpp.jp",
        "password": "AIaaSAgent#Pfc2024!",
    },
}

# ─── ONTOLOGIES DE MESSAGES (protocole inter-agents) ─────────────────────────
# Chaque canal de communication a une ontologie unique pour le routage XMPP.
ONTOLOGY = {
    "STOCK_ALERT":         "pharma.stock.alert",
    "PREDICTION_REQUEST":  "pharma.prediction.request",
    "PREDICTION_RESPONSE": "pharma.prediction.response",
    "SAFETY_CHECK":        "pharma.safety.check",
    "SAFETY_ALERT":        "pharma.safety.alert",
    "AIAAS_REQUEST":       "pharma.aiaas.request",
    "AIAAS_RESPONSE":      "pharma.aiaas.response",
}

# ─── DATASET ─────────────────────────────────────────────────────────────────
DATASET_PATH       = "data/pharma_mas_processed.csv"
DATASET_PATH_RAW   = "data/pharma_mas_dataset.csv"
AI_MODELS_DIR      = "ai_models/"
RESULTS_DIR        = "results/"

# ─── SIMULATION ──────────────────────────────────────────────────────────────
TICK_INTERVAL_SECONDS   = 1      # Délai entre chaque snapshot quotidien
STARTUP_DELAY_SECONDS   = 3      # Attente pour que tous les agents soient en ligne
START_DATE              = "2023-01-01"
END_DATE                = "2024-12-31"

# ─── SEUILS DE DÉCISION ───────────────────────────────────────────────────────
NEAR_EXPIRY_THRESHOLD_DAYS = 30   # <= 30j → alerte péremption
LOW_STOCK_PCT              = 0.20  # <= 20% capacité → stock critique
CRITICAL_LOW_STOCK_PCT     = 0.05  # <= 5%  → transfert d'urgence immédiat
FORECAST_HORIZON_DAYS      = 7    # Prédiction sur 7 jours glissants

# ─── API ANTHROPIC (AIaaSAgent) ───────────────────────────────────────────────
# Laissez vide pour utiliser le mode SIMULÉ (pas d'appel API réel).
# Renseignez votre clé pour activer les recommandations IA réelles.
ANTHROPIC_API_KEY   = ""
AIAAS_MODEL         = "claude-sonnet-4-20250514"
AIAAS_MAX_TOKENS    = 512
AIAAS_SIMULATE_MODE = True  # Basculez à False si ANTHROPIC_API_KEY est renseignée