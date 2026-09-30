# ⬡ Dynamic DAG Multi-Agent Code Generation Studio

An autonomous, multi-agent AI system for advanced code generation. The studio
dynamically decomposes a complex user query into an optimal **Directed Acyclic
Graph (DAG)** of subtasks, spawns specialized agents on-the-fly with custom
personas and toolsets, and executes independent tasks **concurrently in parallel**
while streaming every event to a live web UI.

## Features

- **Dynamic planning & decomposition** — a planner turns a natural-language
  query into a validated DAG (cycle-checked, dependency-ordered).
- **Async parallel DAG execution** — a topological scheduler runs all
  *ready* nodes concurrently with `asyncio`, tracking peak parallelism.
- **Specialized agent personas** — architect, backend/frontend engineer, DBA,
  security, QA, DevOps, ML engineer, technical writer — each with its own
  toolset (`write_file`, `shell`, `search`).
- **Live web UI** — real-time DAG visualization, agent cards, event stream,
  and a file explorer with syntax highlighting.
- **Zero-config demo mode** — a built-in mock LLM provider plans and generates
  realistic code locally. Optionally route through any OpenAI-compatible API.

## Quick start

```bash
cd dag-studio
pip install -r requirements.txt
python run.py
# open http://localhost:8000
```

Try an example query:

> A realtime team chat web app with auth, database and tests

## How it works

```
User query
   │
   ▼
┌─────────────┐   DAG spec (JSON)   ┌──────────────────┐
│   Planner   │ ──────────────────► │  DAG validator   │
│  (LLM)      │                     │  (cycle check)   │
└─────────────┘                     └────────┬─────────┘
                                             │ nodes + edges
                                             ▼
                                ┌────────────────────────┐
                                │  Parallel DAG executor │
                                │  (Kahn-ready set +     │
                                │   asyncio.gather)      │
                                └────────┬───────────────┘
                          ┌──────────────┼──────────────┐
                          ▼              ▼              ▼
                    Agent: arch    Agent: dba     Agent: backend
                    (persona +     (persona +     (persona +
                     toolset)       toolset)       toolset)
                          └──────────────┼──────────────┘
                                         ▼
                              Artifacts → workspace/<run_id>/
                                         ▼
                              WebSocket event stream → UI
```

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `LLM_PROVIDER` | `mock` | `mock` (local) or `openai` |
| `OPENAI_API_KEY` | — | API key for OpenAI-compatible provider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Endpoint (works with Ollama etc.) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/run` | Start a run `{ "query": "..." }` |
| `POST` | `/api/run/{id}/cancel` | Cancel the active run |
| `GET` | `/api/run/{id}` | Current DAG state |
| `GET` | `/api/run/{id}/files` | Generated file list |
| `GET` | `/api/run/{id}/file?path=...` | File contents |
| `WS` | `/ws` | Live event stream |

## Project layout

```
dag-studio/
├── run.py               # entry point
├── requirements.txt
├── server/
│   ├── main.py          # FastAPI app, REST + WebSocket
│   ├── planner.py       # query → DAG decomposition
│   ├── dag.py           # DAG model, scheduler, layout
│   ├── executor.py      # async parallel executor + stats
│   ├── agents.py        # personas, toolsets, agent loop
│   ├── llm.py           # provider abstraction (mock + OpenAI)
│   ├── codegen.py       # local planning & code generation
│   ├── workspace.py     # artifact persistence
│   └── events.py        # pub/sub event bus
└── static/
    ├── index.html       # UI shell
    ├── styles.css       # dark theme
    └── app.js           # WebSocket client, DAG renderer
```
