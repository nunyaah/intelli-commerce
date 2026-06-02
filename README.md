# IntelliCommerce

AI-powered e-commerce intelligence platform. Real-time data generators feed a LangGraph ReAct agent, with semantic ticket search, anomaly detection, HITL alerts, and a live React dashboard.

## Quick Start

```bash
git clone <repo-url>
cd intelli-commerce
cp .env.example .env        # paste your GROQ_API_KEY
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Langfuse | http://localhost:3001 |
| ChromaDB | http://localhost:8001 |

## Architecture

```
Data Generators ──► SQLite ──► Pipeline ──► ChromaDB (ticket embeddings)
                                  │
                                  ▼
                        FastAPI (REST + SSE)
                                  │
                        LangGraph ReAct Agent
                        ├── query_orders   (SQL)
                        ├── search_tickets (RAG / ChromaDB)
                        ├── get_metrics    (KPI aggregates)
                        ├── detect_anomaly (z-score)
                        └── web_search     (DuckDuckGo)
                                  │
                           React Dashboard
```

## Services

| Container | Purpose |
|---|---|
| `ic-generator` | Produces orders, tickets, anomaly events |
| `ic-pipeline` | Ingests, aggregates KPIs, embeds tickets every 30s |
| `ic-api` | FastAPI — REST + Server-Sent Events streaming |
| `ic-chromadb` | Vector store for RAG ticket search |
| `ic-redis` | 60s tool-result cache (Groq rate-limit protection) |
| `ic-langfuse` | LLM observability (traces, cost, latency) |
| `ic-frontend` | React + Vite dashboard served via nginx |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Free at console.groq.com — llama-3.1-8b |

## CI/CD

- **CI** (`.github/workflows/ci.yml`): runs on every push/PR — lints Python with ruff, builds both Docker images to verify they compile
- **CD** (`.github/workflows/cd.yml`): runs on push to `main` or version tags — builds and pushes images to **GitHub Container Registry** (`ghcr.io`) using `GITHUB_TOKEN` (no secrets needed)

To pull a pre-built image instead of building locally:
```bash
docker pull ghcr.io/<your-username>/intellicommerce-api:main
docker pull ghcr.io/<your-username>/intellicommerce-frontend:main
```
