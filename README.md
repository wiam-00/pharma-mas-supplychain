# Pharmaceutical Supply Chain Multi-Agent System (Pharma-MAS)

##  System Overview
This project deploys an asynchronous Multi-Agent System (MAS) leveraging **SPADE v4.1.4** to monitor pharmaceutical inventories, detect stockouts, flag near-expiry batches, and automate cross-pharmacy or supplier logistics routing. 

It now includes an **AIaaS (AI-as-a-Service) Gateway** built with FastAPI to seamlessly expose agent decisions, inventory statuses, and machine learning predictions to external dashboard applications.

---

##  Technology Stack
- **Core MAS Framework:** SPADE v4.1.4 (Asynchronous Python Agent Development)
- **AIaaS Gateway Layer:** FastAPI & FastAPIOffline (Local Swagger/ReDoc OpenAPI generation)
- **Language Runtime:** Python 3.10.x
- **Network Messaging Protocol:** XMPP via local orchestration server (**Openfire Server**)
- **Data Analytics & ML:** Pandas & LSTM Demand Forecaster
- **Asynchronous WSGI Server:** Uvicorn

---

##  Architecture Design
The ecosystem is split into two primary operational layers communicating asynchronously:
1. **The Backend MAS Core:** 7 specialized SPADE agents handling stock behavior, threshold monitoring, and supplier fulfillment. The output of each simulation cycle is written into `results/decision_report.json`.
2. **The AIaaS Gateway (FastAPI):** Reads the generated simulation state and serves standardized REST endpoints (`/api/stocks`, `/api/predictions`, `/api/orders`) wrapped in an offline-ready Swagger UI interface.

---

##  Execution & Deployment Instructions

### 1. Prerequisites & Environment Activation
Ensure your Anaconda environment is isolated and properly activated:
```bash
conda activate pfc_env
