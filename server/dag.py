"""Directed Acyclic Graph model: nodes, edges, validation, scheduling and
layered layout used by both the executor and the UI renderer."""
from __future__ import annotations

import dataclasses
import enum
import uuid
from typing import Any


class NodeStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclasses.dataclass
class TaskNode:
    id: str
    title: str
    description: str
    persona: str
    toolset: list[str] = dataclasses.field(default_factory=list)
    depends_on: list[str] = dataclasses.field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: str = ""
    artifacts: list[str] = dataclasses.field(default_factory=list)
    error: str = ""
    started_at: float | None = None
    finished_at: float | None = None
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class DagValidationError(Exception):
    pass


class Dag:
    def __init__(self, query: str, label: str = "") -> None:
        self.id = uuid.uuid4().hex[:12]
        self.query = query
        self.label = label or query[:60]
        self.nodes: dict[str, TaskNode] = {}
        self.created_at: float | None = None
        self.finished_at: float | None = None

    # ------------------------------------------------------------------ build
    def add_node(self, node: TaskNode) -> TaskNode:
        if node.id in self.nodes:
            raise DagValidationError(f"duplicate node id: {node.id}")
        self.nodes[node.id] = node
        return node

    def add_edge(self, from_id: str, to_id: str) -> None:
        if from_id not in self.nodes or to_id not in self.nodes:
            raise DagValidationError("edge references unknown node")
        if from_id == to_id:
            raise DagValidationError("self-loop detected")
        if from_id not in self.nodes[to_id].depends_on:
            self.nodes[to_id].depends_on.append(from_id)

    def validate(self) -> None:
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise DagValidationError(
                        f"node {node.id} depends on unknown node {dep}"
                    )
        # cycle detection via DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in self.nodes}

        def visit(nid: str) -> None:
            color[nid] = GRAY
            for dep in self.nodes[nid].depends_on:
                if color[dep] == GRAY:
                    raise DagValidationError("cycle detected in DAG")
                if color[dep] == WHITE:
                    visit(dep)
            color[nid] = BLACK

        for nid in self.nodes:
            if color[nid] == WHITE:
                visit(nid)

    # -------------------------------------------------------------- scheduling
    def ready_nodes(self) -> list[TaskNode]:
        """Nodes whose dependencies are all completed."""
        out = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            if all(
                self.nodes[dep].status == NodeStatus.COMPLETED
                for dep in node.depends_on
            ):
                out.append(node)
        return out

    def has_finished(self) -> bool:
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
            for n in self.nodes.values()
        )

    def roots(self) -> list[TaskNode]:
        return [n for n in self.nodes.values() if not n.depends_on]

    # ---------------------------------------------------------------- layout
    def layout(self) -> dict[str, dict[str, float]]:
        """Layered (Sugiyama-lite) layout: layer = longest path from a root."""
        layer: dict[str, int] = {}

        def depth(nid: str) -> int:
            if nid in layer:
                return layer[nid]
            deps = self.nodes[nid].depends_on
            d = 0 if not deps else max(depth(dep) for dep in deps) + 1
            layer[nid] = d
            return d

        for nid in self.nodes:
            depth(nid)

        per_layer: dict[int, list[str]] = {}
        for nid, lyr in layer.items():
            per_layer.setdefault(lyr, []).append(nid)

        pos: dict[str, dict[str, float]] = {}
        for lyr, ids in per_layer.items():
            ids.sort()
            for i, nid in enumerate(ids):
                pos[nid] = {
                    "x": 80 + lyr * 260,
                    "y": 70 + i * 130,
                    "layer": lyr,
                }
        return pos

    # ----------------------------------------------------------------- state
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "label": self.label,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "layout": self.layout(),
        }
