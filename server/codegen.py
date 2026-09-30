"""Local code generation used by the mock LLM provider.

This is what makes the studio fully functional with zero configuration:
it decomposes a natural-language query into a DAG of specialized tasks and
generates realistic source files for each task.
"""
from __future__ import annotations

import re


# --------------------------------------------------------------------- helpers
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "app"


def _stack_hints(query: str) -> dict[str, bool]:
    q = query.lower()
    return {
        "web": any(k in q for k in ("web", "site", "page", "ui", "frontend", "app")),
        "api": any(k in q for k in ("api", "backend", "server", "rest", "endpoint")),
        "db": any(k in q for k in ("database", "db", "sql", "data", "store", "persist")),
        "auth": any(k in q for k in ("auth", "login", "user", "account", "jwt", "oauth")),
        "test": any(k in q for k in ("test", "quality", "qa", "coverage")),
        "deploy": any(k in q for k in ("deploy", "docker", "ci", "cd", "cloud", "k8s", "kubernetes")),
        "docs": any(k in q for k in ("doc", "readme", "guide", "spec")),
        "ml": any(k in q for k in ("ml", "model", "ai", "predict", "train", "llm")),
        "pay": any(k in q for k in ("pay", "stripe", "checkout", "billing", "subscription")),
        "realtime": any(k in q for k in ("realtime", "real-time", "websocket", "chat", "live", "socket")),
    }


# ------------------------------------------------------------------ DAG plan
def plan_from_prompt(prompt: str) -> dict:
    """Return a DAG spec (nodes + edges) for a user query."""
    q = prompt.lower()
    hints = _stack_hints(q)
    name = _slug(prompt.split(" that ")[0][:40])

    nodes: list[dict] = []
    edges: list[tuple[str, str]] = []

    def add(nid, title, desc, persona, tools, deps=()):
        nodes.append(
            {
                "id": nid,
                "title": title,
                "description": desc,
                "persona": persona,
                "toolset": list(tools),
                "depends_on": list(deps),
            }
        )
        for d in deps:
            edges.append((d, nid))

    # 1. Architecture is always the root
    add(
        "arch",
        "System Architecture",
        f"Decompose '{prompt[:80]}' into components, interfaces and data flow.",
        "architect",
        ["search", "write_file"],
    )

    # 2. Parallel tracks fanning out of architecture
    if hints["db"]:
        add(
            "schema",
            "Database Schema & Models",
            "Design tables, indexes, relationships and ORM models.",
            "dba",
            ["write_file", "search"],
            ["arch"],
        )
    if hints["api"]:
        add(
            "backend",
            "Backend API Services",
            "Implement REST endpoints, business logic and validation.",
            "backend-engineer",
            ["write_file", "shell", "search"],
            ["arch"] + (["schema"] if hints["db"] else []),
        )
    if hints["web"]:
        add(
            "frontend",
            "Frontend UI",
            "Build the user interface, state management and API client.",
            "frontend-engineer",
            ["write_file", "shell", "search"],
            ["arch"] + (["backend"] if hints["api"] else []),
        )
    if hints["auth"]:
        add(
            "auth",
            "Authentication & Authorization",
            "JWT sessions, protected routes and role-based access.",
            "security-engineer",
            ["write_file", "search"],
            ["backend"] if hints["api"] else ["arch"],
        )
    if hints["realtime"]:
        add(
            "realtime",
            "Realtime Layer",
            "WebSocket gateway with rooms, presence and reconnection logic.",
            "backend-engineer",
            ["write_file", "shell"],
            ["backend"] if hints["api"] else ["arch"],
        )
    if hints["ml"]:
        add(
            "ml",
            "ML Pipeline",
            "Model loading, inference endpoint and evaluation harness.",
            "ml-engineer",
            ["write_file", "shell"],
            ["backend"] if hints["api"] else ["arch"],
        )
    if hints["pay"]:
        add(
            "billing",
            "Payments & Billing",
            "Checkout flow, webhook handling and subscription state.",
            "backend-engineer",
            ["write_file", "search"],
            ["backend"] if hints["api"] else ["arch"],
        )

    # 3. Convergence tracks
    if hints["test"]:
        deps = [n for n in ("backend", "frontend", "api") if any(nd["id"] == n for nd in nodes)]
        deps = [d for d in deps if d != "api"]
        add(
            "tests",
            "Test Suite",
            "Unit, integration and end-to-end tests with coverage report.",
            "qa-engineer",
            ["write_file", "shell"],
            deps or ["arch"],
        )
    if hints["deploy"]:
        add(
            "infra",
            "Infrastructure & CI/CD",
            "Dockerfiles, compose stack, CI pipeline and deploy scripts.",
            "devops-engineer",
            ["write_file", "shell"],
            [n["id"] for n in nodes if n["id"] != "arch"] or ["arch"],
        )
    if hints["docs"]:
        add(
            "docs",
            "Documentation",
            "README, API reference and architecture decision records.",
            "technical-writer",
            ["write_file", "search"],
            [n["id"] for n in nodes if n["id"] != "arch"][-3:] or ["arch"],
        )

    # Guarantee at least a minimal pipeline for very short/vague queries
    if len(nodes) < 3:
        add(
            "backend",
            "Core Implementation",
            f"Implement the core logic for: {prompt[:80]}",
            "backend-engineer",
            ["write_file", "shell"],
            ["arch"],
        )
        add(
            "tests",
            "Verification",
            "Write tests and verify the implementation works.",
            "qa-engineer",
            ["write_file", "shell"],
            ["backend"],
        )

    return {"name": name, "nodes": nodes, "edges": [list(e) for e in edges]}


def explain_task(prompt: str) -> str:
    return (
        f"Task understood: {prompt[:120]}. I will analyze the requirements, "
        "design the implementation, write the code and verify it works."
    )


# ------------------------------------------------------------- file templates
def _title(query: str) -> str:
    return " ".join(w.capitalize() for w in _slug(query).split("-")[:4])


def _arch_files(query: str) -> list[tuple[str, str]]:
    name = _slug(query)
    return [
        (
            "docs/architecture.md",
            f"""# {_title(query)} — Architecture

## Overview
This document describes the high-level architecture of **{query}**.

## Components

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| API Gateway | Routing, rate limiting, auth | FastAPI |
| Service Layer | Business logic | Python 3.12 |
| Data Layer | Persistence & caching | PostgreSQL + Redis |
| Client | User interface | React + TypeScript |

## Data Flow

```
Client → API Gateway → Service Layer → Data Layer
                ↓
         Auth / Validation
```

## Design Decisions

1. **Modular monolith first** — services are bounded contexts that can be
   extracted into microservices later without rewriting call sites.
2. **Async everywhere** — I/O-bound work uses `asyncio` to maximize
   throughput under concurrent load.
3. **Schema-first contracts** — API schemas are generated from Pydantic
   models so the client and server never drift.

## Non-Functional Requirements

- p95 latency < 200 ms for read endpoints
- 99.9% availability target
- Horizontal scaling via stateless service replicas
""",
        ),
        (
            "docs/adr/001-modular-monolith.md",
            """# ADR 001: Modular Monolith Over Microservices

## Status
Accepted

## Context
The system needs to ship fast but may grow beyond a single deployable.

## Decision
Start with a modular monolith: strictly separated bounded contexts inside
one deployable, with clear internal interfaces.

## Consequences
- Positive: simple deployment, fast local development, easy refactoring.
- Negative: scaling is per-deployable, not per-context.
- Mitigation: contexts communicate through interfaces, never direct imports
  across context boundaries.
""",
        ),
    ]


def _schema_files(query: str) -> list[tuple[str, str]]:
    name = _slug(query)
    return [
        (
            "migrations/001_init.sql",
            f"""-- Initial schema for {_title(query)}
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member'
                  CHECK (role IN ('admin', 'member')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE items (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    metadata   JSONB NOT NULL DEFAULT '{{}}',
    position   INT  NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_owner   ON projects (owner_id);
CREATE INDEX idx_items_project    ON items (project_id);
CREATE INDEX idx_items_metadata   ON items USING GIN (metadata);
""",
        ),
        (
            "app/db/models.py",
            '"""SQLAlchemy models."""\n'
            "from sqlalchemy import JSON, ForeignKey, String, Text\n"
            "from sqlalchemy.dialects.postgresql import UUID\n"
            "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship\n"
            "import uuid\n\n\n"
            "class Base(DeclarativeBase):\n    pass\n\n\n"
            "class User(Base):\n"
            '    __tablename__ = "users"\n\n'
            "    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)\n"
            "    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)\n"
            "    display_name: Mapped[str] = mapped_column(String(120))\n"
            "    role: Mapped[str] = mapped_column(String(20), default='member')\n"
            "    projects: Mapped[list['Project']] = relationship(back_populates='owner', cascade='all, delete-orphan')\n\n\n"
            "class Project(Base):\n"
            '    __tablename__ = "projects"\n\n'
            "    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)\n"
            "    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), index=True)\n"
            "    name: Mapped[str] = mapped_column(String(200))\n"
            "    description: Mapped[str] = mapped_column(Text, default='')\n"
            "    owner: Mapped['User'] = relationship(back_populates='projects')\n"
            "    items: Mapped[list['Item']] = relationship(back_populates='project', cascade='all, delete-orphan')\n\n\n"
            "class Item(Base):\n"
            '    __tablename__ = "items"\n\n'
            "    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)\n"
            "    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('projects.id'), index=True)\n"
            "    title: Mapped[str] = mapped_column(String(300))\n"
            "    metadata: Mapped[dict] = mapped_column(JSON, default=dict)\n"
            "    project: Mapped['Project'] = relationship(back_populates='items')\n",
        ),
    ]


def _backend_files(query: str) -> list[tuple[str, str]]:
    name = _slug(query)
    return [
        (
            "app/main.py",
            '"""Application entry point."""\n'
            "from contextlib import asynccontextmanager\n\n"
            "from fastapi import FastAPI\n"
            "from fastapi.middleware.cors import CORSMiddleware\n\n"
            "from .db.session import engine\n"
            "from .db.models import Base\n"
            "from .api.router import api_router\n\n\n"
            "@asynccontextmanager\n"
            "async def lifespan(app: FastAPI):\n"
            "    async with engine.begin() as conn:\n"
            "        await conn.run_sync(Base.metadata.create_all)\n"
            "    yield\n\n\n"
            "app = FastAPI(title='{_title(query)}', version='0.1.0', lifespan=lifespan)\n\n"
            "app.add_middleware(\n"
            "    CORSMiddleware,\n"
            "    allow_origins=['*'],\n"
            "    allow_methods=['*'],\n"
            "    allow_headers=['*'],\n"
            ")\n\n"
            "app.include_router(api_router, prefix='/api')\n\n\n"
            "@app.get('/health')\n"
            "async def health() -> dict:\n"
            "    return {'status': 'ok'}\n",
        ),
        (
            "app/api/routes.py",
            '"""REST endpoints."""\n'
            "from uuid import UUID\n\n"
            "from fastapi import APIRouter, Depends, HTTPException, Query\n"
            "from pydantic import BaseModel, Field\n"
            "from sqlalchemy.ext.asyncio import AsyncSession\n\n"
            "from .deps import get_db, get_current_user\n\n\n"
            "router = APIRouter()\n\n\n"
            "class ProjectCreate(BaseModel):\n"
            "    name: str = Field(min_length=1, max_length=200)\n"
            "    description: str = Field(default='', max_length=2000)\n\n\n"
            "class ProjectOut(BaseModel):\n"
            "    id: UUID\n"
            "    name: str\n"
            "    description: str\n\n\n"
            "@router.get('/projects', response_model=list[ProjectOut])\n"
            "async def list_projects(\n"
            "    db: AsyncSession = Depends(get_db),\n"
            "    user=Depends(get_current_user),\n"
            "    limit: int = Query(50, ge=1, le=200),\n"
            "):\n"
            "    from sqlalchemy import select\n"
            "    from ..db.models import Project\n\n"
            "    stmt = select(Project).where(Project.owner_id == user.id).limit(limit)\n"
            "    return (await db.scalars(stmt)).all()\n\n\n"
            "@router.post('/projects', response_model=ProjectOut, status_code=201)\n"
            "async def create_project(\n"
            "    payload: ProjectCreate,\n"
            "    db: AsyncSession = Depends(get_db),\n"
            "    user=Depends(get_current_user),\n"
            "):\n"
            "    from ..db.models import Project\n\n"
            "    project = Project(owner_id=user.id, **payload.model_dump())\n"
            "    db.add(project)\n"
            "    await db.commit()\n"
            "    await db.refresh(project)\n"
            "    return project\n\n\n"
            "@router.delete('/projects/{project_id}', status_code=204)\n"
            "async def delete_project(\n"
            "    project_id: UUID,\n"
            "    db: AsyncSession = Depends(get_db),\n"
            "    user=Depends(get_current_user),\n"
            "):\n"
            "    from sqlalchemy import select\n"
            "    from ..db.models import Project\n\n"
            "    project = await db.scalar(select(Project).where(Project.id == project_id))\n"
            "    if not project or project.owner_id != user.id:\n"
            "        raise HTTPException(404, 'project not found')\n"
            "    await db.delete(project)\n"
            "    await db.commit()\n",
        ),
        (
            "app/api/deps.py",
            '"""Shared dependencies."""\n'
            "from fastapi import Depends, HTTPException\n"
            "from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer\n"
            "from sqlalchemy.ext.asyncio import AsyncSession\n\n"
            "from ..db.session import SessionLocal\n\n\n"
            "bearer = HTTPBearer(auto_error=False)\n\n\n"
            "async def get_db():\n"
            "    async with SessionLocal() as session:\n"
            "        yield session\n\n\n"
            "async def get_current_user(\n"
            "    creds: HTTPAuthorizationCredentials | None = Depends(bearer),\n"
            "):\n"
            "    if creds is None:\n"
            "        raise HTTPException(401, 'missing credentials')\n"
            "    # Token verification happens in the auth service\n"
            "    from ..services.auth import verify_token\n\n"
            "    return verify_token(creds.credentials)\n",
        ),
    ]


def _frontend_files(query: str) -> list[tuple[str, str]]:
    name = _slug(query)
    return [
        (
            "web/src/App.tsx",
            'import { useEffect, useState } from "react";\n'
            'import { api } from "./lib/api";\n\n\n'
            "interface Project {\n"
            "  id: string;\n"
            "  name: string;\n"
            "  description: string;\n"
            "}\n\n\n"
            "export default function App() {\n"
            "  const [projects, setProjects] = useState<Project[]>([]);\n"
            "  const [name, setName] = useState('');\n\n"
            "  useEffect(() => {\n"
            "    api.listProjects().then(setProjects).catch(console.error);\n"
            "  }, []);\n\n"
            "  async function create(e: React.FormEvent) {\n"
            "    e.preventDefault();\n"
            "    const created = await api.createProject({ name });\n"
            "    setProjects((p) => [...p, created]);\n"
            "    setName('');\n"
            "  }\n\n"
            "  return (\n"
            "    <main className=\"container\">\n"
            "      <h1>{_title(query)}</h1>\n"
            "      <form onSubmit={create}>\n"
            "        <input value={name} onChange={(e) => setName(e.target.value)} placeholder=\"New project\" />\n"
            "        <button type=\"submit\">Create</button>\n"
            "      </form>\n"
            "      <ul>\n"
            "        {projects.map((p) => (\n"
            "          <li key={p.id}><strong>{p.name}</strong> — {p.description}</li>\n"
            "        ))}\n"
            "      </ul>\n"
            "    </main>\n"
            "  );\n"
            "}\n",
        ),
        (
            "web/src/lib/api.ts",
            'const BASE = import.meta.env.VITE_API_URL ?? "/api";\n\n\n'
            "async function request<T>(path: string, init?: RequestInit): Promise<T> {\n"
            "  const resp = await fetch(`${BASE}${path}`, {\n"
            "    headers: { \"Content-Type\": \"application/json\" },\n"
            "    ...init,\n"
            "  });\n"
            "  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);\n"
            "  return resp.json() as Promise<T>;\n"
            "}\n\n\n"
            "export const api = {\n"
            "  listProjects: () => request<Array<{ id: string; name: string; description: string }>>(\"/projects\"),\n"
            "  createProject: (body: { name: string }) =>\n"
            "    request<{ id: string; name: string; description: string }>(\"/projects\", {\n"
            "      method: \"POST\",\n"
            "      body: JSON.stringify(body),\n"
            "    }),\n"
            "};\n",
        ),
        (
            "web/src/styles.css",
            ":root {\n"
            "  --bg: #0f172a;\n"
            "  --fg: #e2e8f0;\n"
            "  --accent: #6366f1;\n"
            "}\n\n"
            "* { box-sizing: border-box; }\n\n"
            "body {\n"
            "  margin: 0;\n"
            "  font-family: system-ui, sans-serif;\n"
            "  background: var(--bg);\n"
            "  color: var(--fg);\n"
            "}\n\n"
            ".container { max-width: 720px; margin: 0 auto; padding: 2rem 1rem; }\n\n"
            "input, button {\n"
            "  padding: 0.5rem 0.75rem;\n"
            "  border-radius: 0.5rem;\n"
            "  border: 1px solid #334155;\n"
            "  background: #1e293b;\n"
            "  color: var(--fg);\n"
            "}\n\n"
            "button { background: var(--accent); border: none; cursor: pointer; }\n\n"
            "ul { list-style: none; padding: 0; }\n\n"
            "li { padding: 0.75rem; border: 1px solid #334155; border-radius: 0.5rem; margin-top: 0.5rem; }\n",
        ),
    ]


def _auth_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "app/services/auth.py",
            '"""JWT authentication service."""\n'
            "from datetime import datetime, timedelta, timezone\n"
            "from uuid import UUID\n\n"
            "import jwt\n"
            "from pydantic import BaseModel\n\n"
            "SECRET = 'change-me-in-production'\n"
            "ALGORITHM = 'HS256'\n"
            "TTL = timedelta(hours=24)\n\n\n"
            "class TokenPayload(BaseModel):\n"
            "    sub: UUID\n"
            "    role: str\n"
            "    exp: datetime\n\n\n"
            "def create_token(user_id: UUID, role: str) -> str:\n"
            "    payload = TokenPayload(\n"
            "        sub=user_id,\n"
            "        role=role,\n"
            "        exp=datetime.now(timezone.utc) + TTL,\n"
            "    )\n"
            "    return jwt.encode(payload.model_dump(), SECRET, algorithm=ALGORITHM)\n\n\n"
            "def verify_token(token: str) -> TokenPayload:\n"
            "    data = jwt.decode(token, SECRET, algorithms=[ALGORITHM])\n"
            "    return TokenPayload(**data)\n",
        ),
        (
            "app/api/auth_routes.py",
            '"""Auth endpoints."""\n'
            "from fastapi import APIRouter, HTTPException\n"
            "from pydantic import BaseModel, EmailStr\n\n"
            "from ..services.auth import create_token\n\n\n"
            "router = APIRouter()\n\n\n"
            "class LoginIn(BaseModel):\n"
            "    email: EmailStr\n"
            "    password: str\n\n\n"
            "class LoginOut(BaseModel):\n"
            "    token: str\n"
            "    role: str\n\n\n"
            "@router.post('/auth/login', response_model=LoginOut)\n"
            "async def login(payload: LoginIn):\n"
            "    # Credential verification against the users table\n"
            "    user = await authenticate(payload.email, payload.password)\n"
            "    if user is None:\n"
            "        raise HTTPException(401, 'invalid credentials')\n"
            "    return LoginOut(token=create_token(user.id, user.role), role=user.role)\n",
        ),
    ]


def _realtime_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "app/ws/gateway.py",
            '"""WebSocket gateway with rooms and presence."""\n'
            "import json\n\n"
            "from fastapi import WebSocket, WebSocketDisconnect\n\n\n"
            "class ConnectionManager:\n"
            "    def __init__(self):\n"
            "        self.rooms: dict[str, set[WebSocket]] = {}\n\n"
            "    async def join(self, room: str, ws: WebSocket):\n"
            "        await ws.accept()\n"
            "        self.rooms.setdefault(room, set()).add(ws)\n\n"
            "    async def leave(self, room: str, ws: WebSocket):\n"
            "        self.rooms.get(room, set()).discard(ws)\n\n"
            "    async def broadcast(self, room: str, message: dict):\n"
            "        dead = []\n"
            "        for ws in self.rooms.get(room, set()):\n"
            "            try:\n"
            "                await ws.send_text(json.dumps(message))\n"
            "            except Exception:\n"
            "                dead.append(ws)\n"
            "        for ws in dead:\n"
            "            self.rooms.get(room, set()).discard(ws)\n\n\n"
            "manager = ConnectionManager()\n\n\n"
            "async def websocket_endpoint(ws: WebSocket, room: str):\n"
            "    await manager.join(room, ws)\n"
            "    try:\n"
            "        while True:\n"
            "            data = await ws.receive_text()\n"
            "            await manager.broadcast(room, {'room': room, 'data': data})\n"
            "    except WebSocketDisconnect:\n"
            "        await manager.leave(room, ws)\n",
        ),
    ]


def _ml_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "ml/inference.py",
            '"""Model inference service."""\n'
            "from functools import lru_cache\n\n"
            "import numpy as np\n\n\n"
            "@lru_cache(maxsize=1)\n"
            "def load_model():\n"
            "    # Load once per process; swap for your framework of choice\n"
            "    from sklearn.dummy import DummyClassifier\n\n"
            "    model = DummyClassifier(strategy='most_frequent')\n"
            "    model.fit(np.zeros((1, 4)), np.zeros(1))\n"
            "    return model\n\n\n"
            "def predict(features: list[float]) -> dict:\n"
            "    model = load_model()\n"
            "    x = np.asarray(features, dtype=float).reshape(1, -1)\n"
            "    proba = model.predict_proba(x)[0]\n"
            "    return {'prediction': int(model.predict(x)[0]), 'confidence': float(max(proba))}\n",
        ),
        (
            "ml/evaluate.py",
            '"""Evaluation harness."""\n'
            "import json\n\n"
            "import numpy as np\n\n"
            "from .inference import predict\n\n\n"
            "def evaluate(dataset_path: str) -> dict:\n"
            "    rows = [json.loads(line) for line in open(dataset_path)]\n"
            "    correct = 0\n"
            "    for row in rows:\n"
            "        out = predict(row['features'])\n"
            "        correct += int(out['prediction'] == row['label'])\n"
            "    return {'n': len(rows), 'accuracy': correct / max(len(rows), 1)}\n",
        ),
    ]


def _billing_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "app/services/billing.py",
            '"""Billing service: checkout, webhooks, subscriptions."""\n'
            "import hmac\n"
            "import hashlib\n\n\n"
            "def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:\n"
            "    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()\n"
            "    return hmac.compare_digest(expected, signature)\n\n\n"
            "async def create_checkout_session(user_id: str, price_id: str) -> dict:\n"
            "    # Delegates to the payment provider; returns a hosted checkout URL\n"
            "    return {'url': f'https://checkout.example.com/session/{user_id}/{price_id}'}\n\n\n"
            "async def handle_webhook(event: dict) -> None:\n"
            "    match event['type']:\n"
            "        case 'checkout.session.completed':\n"
            "            await activate_subscription(event['data']['object'])\n"
            "        case 'customer.subscription.deleted':\n"
            "            await cancel_subscription(event['data']['object'])\n",
        ),
    ]


def _test_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "tests/test_projects.py",
            '"""API tests."""\n'
            "import pytest\n"
            "from httpx import AsyncClient\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_create_project(client: AsyncClient, auth_headers):\n"
            "    resp = await client.post('/api/projects', json={'name': 'Demo'}, headers=auth_headers)\n"
            "    assert resp.status_code == 201\n"
            "    body = resp.json()\n"
            "    assert body['name'] == 'Demo'\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_list_projects_isolated(client: AsyncClient, auth_headers):\n"
            "    resp = await client.get('/api/projects', headers=auth_headers)\n"
            "    assert resp.status_code == 200\n"
            "    assert isinstance(resp.json(), list)\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_unauthorized(client: AsyncClient):\n"
            "    resp = await client.get('/api/projects')\n"
            "    assert resp.status_code == 401\n",
        ),
        (
            "tests/conftest.py",
            '"""Shared fixtures."""\n'
            "import pytest_asyncio\n"
            "from httpx import AsyncClient\n\n"
            "from app.main import app\n\n\n"
            "@pytest_asyncio.fixture\n"
            "async def client():\n"
            "    async with AsyncClient(app=app, base_url='http://test') as ac:\n"
            "        yield ac\n\n\n"
            "@pytest_asyncio.fixture\n"
            "async def auth_headers():\n"
            "    return {'Authorization': 'Bearer test-token'}\n",
        ),
    ]


def _infra_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "Dockerfile",
            'FROM python:3.12-slim AS base\n\n'
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n\n"
            "COPY . .\n\n"
            'EXPOSE 8000\n\n'
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]\n',
        ),
        (
            "docker-compose.yml",
            'services:\n'
            "  api:\n"
            "    build: .\n"
            "    ports: ['8000:8000']\n"
            "    environment:\n"
            "      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/app\n"
            "    depends_on: [db]\n\n"
            "  db:\n"
            "    image: postgres:16-alpine\n"
            "    environment:\n"
            "      POSTGRES_PASSWORD: postgres\n"
            "    ports: ['5432:5432']\n",
        ),
        (
            ".github/workflows/ci.yml",
            'name: CI\n\non: [push, pull_request]\n\njobs:\n'
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v5\n"
            "        with: {python-version: '3.12'}\n"
            "      - run: pip install -r requirements.txt\n"
            "      - run: pytest --cov=app --cov-report=xml\n"
            "      - run: ruff check .\n",
        ),
    ]


def _docs_files(query: str) -> list[tuple[str, str]]:
    return [
        (
            "README.md",
            f"""# {_title(query)}

Generated by the **Dynamic DAG Multi-Agent Code Generation Studio**.

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create a project |
| DELETE | `/api/projects/{{id}}` | Delete a project |

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full design and
[`docs/adr`](docs/adr) for architecture decision records.

## Testing

```bash
pytest --cov=app
```
""",
        ),
    ]


# ------------------------------------------------------------------ dispatch
_GENERATORS = {
    "architect": _arch_files,
    "dba": _schema_files,
    "backend-engineer": _backend_files,
    "frontend-engineer": _frontend_files,
    "security-engineer": _auth_files,
    "qa-engineer": _test_files,
    "devops-engineer": _infra_files,
    "ml-engineer": _ml_files,
    "technical-writer": _docs_files,
}


def generate_files(node, query: str) -> list[tuple[str, str]]:
    """Return [(path, content)] for a DAG node based on its persona."""
    persona = node.persona
    if persona == "backend-engineer" and "realtime" in node.title.lower():
        return _realtime_files(query)
    if persona == "backend-engineer" and "billing" in node.title.lower():
        return _billing_files(query)
    gen = _GENERATORS.get(persona, _backend_files)
    return gen(query)
