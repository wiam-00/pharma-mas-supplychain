import os
import json
from fastapi import FastAPI
from fastapi_offline import FastAPIOffline # Version locale de FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Utilisation directe de FastAPIOffline (gère /docs sans internet ni CDN)
app = FastAPIOffline(
    title="Pharma MAS AIaaS API",
    description="API d'exposition des services IA et du Système Multi-Agents pour la gestion des stocks",
    version="1.0.0"
)

# ─── CONFIGURATION CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chemin absolu sécurisé vers le rapport réel de la simulation
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(BASE_DIR, "results", "decision_report.json")

# ─── DONNÉES FICTIVES DE TEST (MOCK DATA) ─────────────────────────────────
MOCK_STOCKS = [
    {"id": 1, "medicament": "Paracétamol 500mg", "stock_actuel": 45, "seuil_alerte": 50, "etat": "Critique"},
    {"id": 2, "medicament": "Amoxicilline 1g", "stock_actuel": 120, "seuil_alerte": 30, "etat": "Normal"},
    {"id": 3, "medicament": "Ibuprofène 400mg", "stock_actuel": 12, "seuil_alerte": 40, "etat": "Rupture Imminente"}
]

MOCK_PREDICTIONS = [
    {"medicament": "Ibuprofène 400mg", "probabilite_rupture": 0.94, "horizon_jours": 3, "IA_modele": "LSTM_Demand_Forecaster"},
    {"medicament": "Paracétamol 500mg", "probabilite_rupture": 0.78, "horizon_jours": 5, "IA_modele": "LSTM_Demand_Forecaster"}
]

MOCK_ORDERS = [
    {"order_id": "CMD-2026-001", "medicament": "Ibuprofène 400mg", "quantite": 100, "statut": "EN_COURS", "agent_emetteur": "pfc_replenishment_agent"},
    {"order_id": "CMD-2026-002", "medicament": "Paracétamol 500mg", "quantite": 150, "statut": "CONFIRME", "agent_emetteur": "pfc_replenishment_agent"}
]

# ─── ENDPOINTS (ROUTES HTTP) ─────────────────────────────────────────────

@app.get("/")
def health_check():
    """Vérifie que la couche AIaaS fonctionne bien."""
    return {"status": "ONLINE", "message": "Pharma MAS AIaaS API is running smoothly."}

@app.get("/api/status")
def get_system_status():
    """Renvoie l'état global du système multi-agents."""
    return {
        "simulation_mode": "Real/Simulation" if os.path.exists(REPORT_PATH) else "Demo/Mock",
        "total_agents_configured": 7,
        "openfire_server": "localhost:5222",
        "api_layer": "FastAPI"
    }

@app.get("/api/stocks")
def get_stocks():
    """Renvoie l'état des stocks (lit le JSON réel s'il existe, sinon renvoie le Mock)."""
    if os.path.exists(REPORT_PATH):
        try:
            with open(REPORT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("stocks", MOCK_STOCKS)
        except Exception:
            return MOCK_STOCKS
    return MOCK_STOCKS

@app.get("/api/predictions")
def get_predictions():
    """Renvoie les prédictions d'alertes IA."""
    if os.path.exists(REPORT_PATH):
        try:
            with open(REPORT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("predictions", MOCK_PREDICTIONS)
        except Exception:
            return MOCK_PREDICTIONS
    return MOCK_PREDICTIONS

@app.get("/api/orders")
def get_orders():
    """Renvoie l'historique des commandes envoyées aux fournisseurs."""
    if os.path.exists(REPORT_PATH):
        try:
            with open(REPORT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("commandes", MOCK_ORDERS)
        except Exception:
            return MOCK_ORDERS
    return MOCK_ORDERS