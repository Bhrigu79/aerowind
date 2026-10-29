# AEROWIND

**Autonomous AI Performance Engineer**

> Give AEROWIND an AI system and measurable constraints. It will autonomously run experiments, measure real results, detect regressions, and iterate until your constraints are satisfied.

---

## Quick Start

### 1. Clone and set up environment

```bash
cd backend
cp .env.example .env
# Edit .env and add your NEBIUS_API_KEY (required for Nebius/Nemotron)
```

### 2. Start infrastructure (PostgreSQL + Redis)

```bash
docker compose -f infra/docker-compose.dev.yml up postgres redis -d
```

### 3. Install Python dependencies

```bash
cd backend
pip install -e ".[dev]"
```

### 4. Run the backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Open API docs

Navigate to: http://localhost:8000/docs

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `NEBIUS_API_KEY` | **Yes** | Nebius AI Cloud API key (primary provider) |
| `NEBIUS_BASE_URL` | No | Defaults to `https://api.studio.nebius.com/v1` |
| `NEBIUS_DEFAULT_MODEL` | No | Defaults to `nvidia/llama-3.1-nemotron-70b-instruct` |
| `OPENAI_API_KEY` | No | OpenAI API key (fallback provider) |
| `ANTHROPIC_API_KEY` | No | Anthropic API key (fallback provider) |
| `GEMINI_API_KEY` | No | Google Gemini API key (fallback provider) |
| `DATABASE_URL` | No | PostgreSQL URL (defaults to local) |
| `REDIS_URL` | No | Redis URL (defaults to local) |

---

## Architecture

```
Frontend (Next.js)
    ↓
FastAPI API Layer (/api/v1)
    ↓
Agent Orchestrator
    ↓
ModelGateway (central)
    ├── Task-Aware Router
    ├── Provider Health Monitor
    ├── Retry + Fallback
    ├── Usage Tracker
    └── Provider Adapters
         ├── Nebius (NVIDIA Nemotron) ← PRIMARY
         ├── OpenAI
         ├── Anthropic
         └── Gemini
```

**Critical design rule**: Agents NEVER import provider SDKs. All model calls go through `ModelGateway`.

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | API info |
| GET | `/health` | System health + provider status |
| GET | `/docs` | Swagger UI |
| POST | `/api/v1/projects/` | Create optimization project |
| GET | `/api/v1/projects/` | List projects |
| GET | `/api/v1/projects/{id}` | Get project |
| PATCH | `/api/v1/projects/{id}` | Update project |
| POST | `/api/v1/experiments/` | Create experiment |
| GET | `/api/v1/experiments/` | List experiments |
| POST | `/api/v1/experiments/{id}/start` | Start experiment |
| POST | `/api/v1/hypotheses/` | Create hypothesis |
| GET | `/api/v1/hypotheses/` | List hypotheses |
| GET | `/api/v1/gateway/status` | Gateway + provider health |
| POST | `/api/v1/gateway/complete` | Direct model completion (testing) |
| GET | `/api/v1/gateway/usage` | Token/cost usage stats |

---

## Development Phases

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ **Complete** | Backend foundation + FastAPI + Model Gateway |
| 2 | 🔜 Next | Provider adapters verification + first real model call |
| 3 | ⏳ Planned | PostgreSQL + Alembic + persistent state |
| 4 | ⏳ Planned | Agent orchestration (Hypothesis/Experiment/Analysis agents) |
| 5 | ⏳ Planned | Docker sandbox experiment runner |
| 6 | ⏳ Planned | Benchmark/evaluation engine |
| 7 | ⏳ Planned | Autonomous experimentation loop |
| 8 | ⏳ Planned | Architecture evolution |
| 9 | ⏳ Planned | Provider competition + intelligent routing |
| 10 | ⏳ Planned | Premium Next.js frontend |
| 11 | ⏳ Planned | Observability, deployment, polish |

---

## Core Concepts

AEROWIND distinguishes between:

| Concept | Meaning |
|---|---|
| **Hypothesis** | "Parallel execution may reduce P95 latency" |
| **Experiment** | A controlled test of that hypothesis |
| **Measurement** | Actual measured quality/latency/cost/reliability |
| **Result** | Hypothesis confirmed / rejected / inconclusive |
| **Conclusion** | Evidence-backed decision to adopt or discard the change |
| **Evolution** | Architecture-level retained improvement |

---

## License

AEROWIND — Hackathon project. All rights reserved.
