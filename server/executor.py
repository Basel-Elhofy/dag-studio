"""Async parallel DAG executor.

Runs ready nodes concurrently with asyncio, tracks live stats (active
agents, peak parallelism, token estimates) and streams everything to the UI.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .agents import Agent
from .dag import Dag, NodeStatus
from .events import BUS
from .workspace import Workspace


class RunStats:
    def __init__(self) -> None:
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.peak_parallelism = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.artifacts = 0

    def to_dict(self) -> dict[str, Any]:
        elapsed = (self.finished_at or time.time()) - (self.started_at or time.time())
        return {
            "elapsed": round(elapsed, 2),
            "peak_parallelism": self.peak_parallelism,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "artifacts": self.artifacts,
        }


class DagExecutor:
    def __init__(self) -> None:
        self._current: asyncio.Task | None = None
        self._cancel_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._current is not None and not self._current.done()

    def cancel(self) -> None:
        self._cancel_event.set()

    async def run(self, dag: Dag) -> None:
        self._cancel_event.clear()
        ws = Workspace(dag.id)
        stats = RunStats()
        stats.started_at = time.time()
        active: dict[str, Agent] = {}

        await BUS.publish(
            "run.started",
            run_id=dag.id,
            query=dag.query,
            node_count=len(dag.nodes),
        )

        try:
            while not dag.has_finished():
                if self._cancel_event.is_set():
                    for node in dag.nodes.values():
                        if node.status in (NodeStatus.PENDING, NodeStatus.READY):
                            node.status = NodeStatus.SKIPPED
                    await BUS.publish("run.cancelled", run_id=dag.id)
                    break

                ready = dag.ready_nodes()
                if not ready:
                    # Everything remaining is blocked on a failed node
                    for node in dag.nodes.values():
                        if node.status == NodeStatus.PENDING:
                            node.status = NodeStatus.SKIPPED
                            node.error = "dependency failed"
                    break

                for node in ready:
                    node.status = NodeStatus.READY
                await BUS.publish(
                    "dag.status",
                    run_id=dag.id,
                    dag=dag.to_dict(),
                )

                # Launch all ready nodes concurrently
                tasks = []
                for node in ready:
                    agent = Agent(node, dag.id, dag.query)
                    active[node.id] = agent
                    tasks.append(asyncio.create_task(self._run_node(agent, ws, stats)))
                stats.peak_parallelism = max(stats.peak_parallelism, len(tasks))
                stats.artifacts = sum(len(n.artifacts) for n in dag.nodes.values())
                await BUS.publish(
                    "run.stats",
                    run_id=dag.id,
                    active=len(active),
                    stats=stats.to_dict(),
                )
                await asyncio.gather(*tasks, return_exceptions=True)
                for node in ready:
                    active.pop(node.id, None)

            dag.finished_at = time.time()
            stats.finished_at = dag.finished_at
            stats.artifacts = sum(len(n.artifacts) for n in dag.nodes.values())
            await BUS.publish(
                "run.stats",
                run_id=dag.id,
                active=0,
                stats=stats.to_dict(),
            )
            await BUS.publish(
                "run.finished",
                run_id=dag.id,
                stats=stats.to_dict(),
                tree=ws.tree(),
            )
        except asyncio.CancelledError:
            await BUS.publish("run.cancelled", run_id=dag.id)
        finally:
            await BUS.publish("dag.status", run_id=dag.id, dag=dag.to_dict())

    async def _run_node(self, agent: Agent, ws: Workspace, stats: RunStats) -> None:
        """Run one agent, persisting its artifacts to the workspace."""
        try:
            await agent.run()
            # Persist artifacts the agent generated during its run
            for rel_path, content in agent.generated_files:
                await ws.write(rel_path, content)
                stats.tokens_in += len(content) // 4
                stats.tokens_out += len(content) // 4
        except asyncio.CancelledError:
            raise


EXECUTOR = DagExecutor()
