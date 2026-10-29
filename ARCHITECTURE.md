# AEROWIND — Autonomous AI Performance Engineer

## Overview

AEROWIND is an Autonomous AI System Evolution platform. Users provide an AI system, workload, or engineering objective along with measurable constraints. AEROWIND autonomously generates hypotheses, designs experiments, modifies code/configs/prompts/architecture, executes in isolated sandboxes, measures real results, detects regressions, and iterates until constraints are satisfied.

---

## Repository Structure

```
aerowind/
├── backend/                        # Python / FastAPI backend
│   ├── app/
│   │   ├── api/                    # FastAPI routers
│   │   │   ├── v1/
│   │   │   │   ├── projects.py
│   │   │   │   ├── experiments.py
│   │   │   │   ├── hypotheses.py
│   │   │   │   ├── benchmarks.py
│   │   │   │   ├── providers.py
│   │   │   │   └── reports.py
│   │   ├── core/                   # Core configuration, settings, logging
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   ├── db/                     # Database models and migrations
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── gateway/                # Model Gateway (central layer)
│   │   │   ├── gateway.py          # ModelGateway class
│   │   │   ├── router.py           # Task-aware model router
│   │   │   ├── adapters/           # Provider adapters
│   │   │   │   ├── base.py
│   │   │   │   ├── nebius.py       # Nebius / NVIDIA Nemotron
│   │   │   │   ├── openai.py
│   │   │   │   ├── anthropic.py
│   │   │   │   └── gemini.py
│   │   │   ├── health.py           # Provider health monitor
│   │   │   └── usage.py            # Usage tracking
│   │   ├── agents/                 # Agent orchestration
│   │   │   ├── orchestrator.py
│   │   │   ├── base_agent.py
│   │   │   ├── hypothesis_agent.py
│   │   │   ├── experiment_agent.py
│   │   │   ├── analysis_agent.py
│   │   │   └── report_agent.py
│   │   ├── experiments/            # Experiment engine
│   │   │   ├── runner.py
│   │   │   ├── sandbox.py          # Docker sandbox isolation
│   │   │   ├── benchmark.py
│   │   │   └── evaluator.py
│   │   ├── state/                  # State management
│   │   │   ├── project_state.py
│   │   │   └── agent_state.py
│   │   ├── schemas/                # Pydantic schemas
│   │   │   ├── project.py
│   │   │   ├── experiment.py
│   │   │   ├── hypothesis.py
│   │   │   ├── gateway.py
│   │   │   └── metrics.py
│   │   ├── services/               # Business logic services
│   │   │   ├── project_service.py
│   │   │   ├── experiment_service.py
│   │   │   └── report_service.py
│   │   └── main.py                 # FastAPI app entrypoint
│   ├── tests/
│   ├── alembic/                    # DB migrations
│   ├── pyproject.toml
│   └── .env.example
├── frontend/                       # Next.js 14 / TypeScript / Tailwind
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
│   ├── package.json
│   └── tailwind.config.ts
├── infra/                          # Docker compose, K8s, deployment
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── nginx/
├── docs/
└── README.md
```

---

## Data Flow

```
User Input (Objective + Constraints)
    ↓
FastAPI API Layer
    ↓
Agent Orchestrator  ←→  Project/Agent State (PostgreSQL)
    ↓
Hypothesis Agent → Experiment Design
    ↓
Experiment Runner → Docker Sandbox
    ↓
Benchmark Engine → Metrics Collector
    ↓
Analysis Agent → Evidence Store
    ↓
[Loop or] Report Agent → Final Report
```

---

## Model Gateway Architecture

```
Agents
  ↓
ModelGateway
  ├── Task-Aware Router
  ├── Provider Health Monitor
  ├── Rate Limit / Retry Manager
  ├── Usage Tracker
  └── Provider Adapters
       ├── NebiusAdapter (NVIDIA Nemotron)
       ├── OpenAIAdapter
       ├── AnthropicAdapter
       └── GeminiAdapter
```

**Critical rule**: Agents NEVER import provider SDKs directly. All model calls go through `ModelGateway`.

---

## Key Concepts

| Concept | Description |
|---|---|
| **Project** | A user-defined optimization objective with measurable constraints |
| **Hypothesis** | A testable proposition about what might improve the system |
| **Experiment** | A controlled test of a hypothesis with baseline + candidate |
| **Measurement** | Actual measured metrics: quality, latency, cost, reliability |
| **Result** | Hypothesis confirmed / rejected / inconclusive |
| **Conclusion** | Evidence-backed decision on whether to adopt the change |
| **Evolution** | Architecture-level change retained after successful experiments |

---

## Phase Plan

| Phase | Focus |
|---|---|
| 1 | Repo + Backend + FastAPI + Model Gateway skeleton |
| 2 | Provider adapters + first real model call |
| 3 | PostgreSQL + Alembic + persistent state |
| 4 | Agent orchestration |
| 5 | Sandboxed experiment runner |
| 6 | Benchmark/evaluation engine |
| 7 | Autonomous experimentation loop |
| 8 | Architecture evolution |
| 9 | Provider competition + intelligent routing |
| 10 | Premium frontend + live experiment visualization |
| 11 | Observability, reliability, deployment, polish |
