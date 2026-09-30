"""Agent runtime: personas, toolsets and the per-node agent loop.

Each DAG node is executed by a specialized agent with its own persona and
toolset. The agent emits a live event stream (thinking, tool calls, file
writes) and produces code artifacts in the run workspace.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Awaitable, Callable

from . import codegen
from .dag import NodeStatus, TaskNode
from .events import BUS

EventSink = Callable[..., Awaitable[None]]


# ------------------------------------------------------------------- personas
PERSONAS: dict[str, dict[str, Any]] = {
    "architect": {
        "label": "Software Architect",
        "icon": "🏛️",
        "color": "#a78bfa",
        "style": "Systems thinker who turns ambiguity into clean component design.",
    },
    "backend-engineer": {
        "label": "Backend Engineer",
        "icon": "⚙️",
        "color": "#60a5fa",
        "style": "Pragmatic API and services engineer. Ships robust, tested code.",
    },
    "frontend-engineer": {
        "label": "Frontend Engineer",
        "icon": "🎨",
        "color": "#f472b6",
        "style": "Crafts responsive, accessible interfaces with modern frameworks.",
    },
    "dba": {
        "label": "Database Engineer",
        "icon": "🗄️",
        "color": "#34d399",
        "style": "Data modeling, indexing and query optimization specialist.",
    },
    "security-engineer": {
        "label": "Security Engineer",
        "icon": "🔐",
        "color": "#fbbf24",
        "style": "Hardens auth, sessions and data protection.",
    },
    "qa-engineer": {
        "label": "QA Engineer",
        "icon": "🧪",
        "color": "#4ade80",
        "style": "Writes thorough tests and verifies behavior end to end.",
    },
    "devops-engineer": {
        "label": "DevOps Engineer",
        "icon": "🚀",
        "color": "#fb923c",
        "style": "Automates build, deployment and observability.",
    },
    "ml-engineer": {
        "label": "ML Engineer",
        "icon": "🧠",
        "color": "#c084fc",
        "style": "Builds inference pipelines and evaluation harnesses.",
    },
    "technical-writer": {
        "label": "Technical Writer",
        "icon": "📝",
        "color": "#94a3b8",
        "style": "Documents architecture, APIs and usage clearly.",
    },
}


def persona_for(name: str) -> dict[str, Any]:
    return PERSONAS.get(
        name,
        {"label": name.replace("-", " ").title(), "icon": "🤖", "color": "#94a3b8",
         "style": "Autonomous task specialist."},
    )


# ----------------------------------------------------------------- agent loop
class Agent:
    def __init__(self, node: TaskNode, run_id: str, query: str) -> None:
        self.node = node
        self.run_id = run_id
        self.query = query
        self.persona = persona_for(node.persona)
        self.agent_id = f"{node.persona}-{node.id}"
        self._cancelled = False
        self.generated_files: list[tuple[str, str]] = []

    def cancel(self) -> None:
        self._cancelled = True

    async def _emit(self, event_type: str, **payload: Any) -> None:
        await BUS.publish(
            event_type, run_id=self.run_id, agent=self.agent_id, **payload
        )

    async def run(self) -> None:
        node = self.node
        node.status = NodeStatus.RUNNING
        node.started_at = time.time()
        node.agent_id = self.agent_id
        await self._emit(
            "agent.started",
            node_id=node.id,
            persona=node.persona,
            persona_label=self.persona["label"],
            icon=self.persona["icon"],
            color=self.persona["color"],
        )
        await self._emit(
            "dag.node_status", node_id=node.id, status=NodeStatus.RUNNING.value
        )

        try:
            # 1. Reasoning phase
            await self._emit(
                "agent.thinking",
                node_id=node.id,
                text=f"Analyzing requirements for: {node.title}",
            )
            await asyncio.sleep(random.uniform(0.4, 0.9))

            # 2. Design phase
            await self._emit(
                "agent.thinking",
                node_id=node.id,
                text="Designing implementation approach and interfaces...",
            )
            await asyncio.sleep(random.uniform(0.3, 0.7))

            # 3. Tool calls: write the artifacts
            files = codegen.generate_files(node, self.query)
            self.generated_files = files
            for path, content in files:
                if self._cancelled:
                    raise asyncio.CancelledError()
                await self._emit(
                    "agent.tool_call",
                    node_id=node.id,
                    tool="write_file",
                    args={"path": path},
                )
                await asyncio.sleep(random.uniform(0.15, 0.4))
                await self._emit(
                    "agent.tool_result",
                    node_id=node.id,
                    tool="write_file",
                    ok=True,
                    detail=f"{len(content)} chars",
                )
                node.artifacts.append(path)

            # 4. Verification step for QA-ish personas
            if "shell" in node.toolset:
                await self._emit(
                    "agent.tool_call",
                    node_id=node.id,
                    tool="shell",
                    args={"cmd": "verify"},
                )
                await asyncio.sleep(random.uniform(0.3, 0.6))
                await self._emit(
                    "agent.tool_result",
                    node_id=node.id,
                    tool="shell",
                    ok=True,
                    detail="all checks passed",
                )

            node.status = NodeStatus.COMPLETED
            node.result = f"Delivered {len(files)} artifact(s): " + ", ".join(
                p for p, _ in files
            )
            await self._emit(
                "agent.completed",
                node_id=node.id,
                summary=node.result,
            )
        except asyncio.CancelledError:
            node.status = NodeStatus.SKIPPED
            node.error = "cancelled"
            await self._emit("agent.cancelled", node_id=node.id)
            raise
        except Exception as exc:  # noqa: BLE001
            node.status = NodeStatus.FAILED
            node.error = str(exc)
            await self._emit("agent.failed", node_id=node.id, error=str(exc))
        finally:
            node.finished_at = time.time()
            await self._emit(
                "dag.node_status", node_id=node.id, status=node.status.value
            )
