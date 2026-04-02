# Schedule Forensics Tool

A fully **local-only** web application for forensic analysis of Microsoft Project (`.mpp`) schedule files. Zero data leaves your machine — all processing runs in your browser and a local Python server.

## Features

- **Read `.mpp` files** — via MPXJ/JPype; no Microsoft Project installation required
- **CPM analysis** — forward/backward pass with all four relationship types (FS, SS, FF, SF), hard constraints, total float, free float
- **Critical & near-critical path** — colour-coded Gantt chart (Plotly.js)
- **Logic trace graph** — Cytoscape.js precedence network with focal-task subgraph
- **Multi-version diff** — field-level comparison across up to 10 schedule versions
- **DCMA 14-Point Metrics** — all 14 checks with correct denominators
- **NASA compliance checks** — 9 checks per the NASA Schedule Management Handbook
- **10 forensic manipulation patterns** — Baseline Tampering, Actuals Rewriting, Constraint Pinning, Logic Deletion, Lag Laundering, Duration Smoothing, Progress Inflation, Float Harvesting, Near-Critical Suppression, Driving Path Swap
- **"Ask the Schedule"** — rule-based chat panel with 9 supported query intents (no external LLM)
- **Session privacy** — 4-hour TTL with one-click "End Session" data wipe

## Quick Start

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Java | 11+ (JDK, not JRE) |
| Node.js | 18+ |

### Run

```bash
./scripts/start.sh
```

Then open **http://localhost:5173** in your browser.

The script:
1. Checks Python ≥ 3.11, Java ≥ 11, Node ≥ 18
2. Creates a Python virtual environment and installs backend dependencies
3. Installs frontend Node.js dependencies
4. Starts the FastAPI backend on port 8000
5. Starts the Vite dev server on port 5173

Press **Ctrl+C** to stop both servers.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Browser (localhost:5173)            │
│  React 18 + Plotly.js + Cytoscape.js + Recharts    │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP /api/*
┌──────────────────────▼──────────────────────────────┐
│             FastAPI (localhost:8000)                 │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ MPP Parser  │  │ Analysis     │  │  Chat     │  │
│  │ MPXJ/JPype  │  │ CPM · DCMA   │  │  Router   │  │
│  │             │  │ Forensics    │  │  (rules)  │  │
│  └─────────────┘  └──────────────┘  └───────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Session Manager (in-memory, 4h TTL wipe)    │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

All data is stored **in-memory** for the session lifetime. Uploaded `.mpp` files are written to a temporary directory and deleted on session end.

## API Reference

Interactive API docs are available at **http://localhost:8000/docs** after starting the server.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/session/create` | Create a new analysis session |
| POST | `/session/{id}/upload` | Upload `.mpp` files (max 10) |
| GET | `/session/{id}/versions` | List loaded versions |
| POST | `/session/{id}/analyze` | Run CPM on a version |
| POST | `/session/{id}/diff` | Compare two versions |
| GET | `/session/{id}/dcma/{idx}` | DCMA 14-point metrics |
| POST | `/session/{id}/forensics` | Run forensic detection |
| POST | `/session/{id}/chat` | Rule-based schedule query |
| DELETE | `/session/{id}/end` | Wipe all session data |

## Chat Panel — Supported Queries

| Query pattern | Example |
|---|---|
| What is driving [task]? | `What is driving Task 5?` |
| Why did [milestone] slip? | `Why did Phase 2 Complete slip?` |
| Show critical path for version [N] | `Show critical path for version 0` |
| What changed between version [A] and [B]? | `What changed between version 0 and 1?` |
| Flag manipulation risks for [task] | `Flag manipulation risks for Task 10` |
| What is the DCMA score for version [N]? | `What is the DCMA score for version 0?` |
| Top float risks | `Top float risks` |
| Missing logic | `Which tasks have missing logic?` |
| Valid critical path | `Does the project have a valid critical path?` |

## Development

### Backend tests

```bash
pip install -r backend/requirements.txt
pytest backend/tests/ --cov=backend/analysis --cov-fail-under=80 -v
```

### Frontend tests

```bash
cd frontend
npm ci
npm test
npm run lint
```

### CI

GitHub Actions runs on every push:
- **lint-python**: `ruff check`
- **test-python**: `pytest` with ≥80% coverage
- **lint-frontend**: ESLint
- **test-frontend**: Vitest

## Privacy

- `.mpp` files are **never** sent to any external service
- All analysis runs locally (Python + Java)
- Session data is wiped after 4 hours or when you click "End Session"
- `.gitignore` blocks `*.mpp`, `uploads/`, and `session_data/` from being committed

## License

MIT
