"""Dynamic planner: decomposes a user query into a DAG of specialized tasks.

Uses the configured LLM provider (mock by default) to produce a DAG spec,
then validates and materializes it into a Dag object.
"""
from __future__ import annotations

import time

from . import codegen
from .dag import Dag, TaskNode
from .events import BUS
from .llm import get_provider

PROVIDER = get_provider()


async def plan_dag(query: str) -> Dag:
    await BUS.publish("planner.started", query=query, provider=PROVIDER.name)

    spec = await PROVIDER.complete(
        [
            {
                "role": "system",
                "content": (
                    "You are a planning engine. Decompose the user's software "
                    "request into a DAG of specialized tasks. Output JSON with "
                    "keys: name (slug), nodes (id, title, description, persona, "
                    "toolset, depends_on), edges ([from, to]). Keep 4-10 nodes."
                ),
            },
            {"role": "user", "content": query},
        ],
        json_mode=True,
        temperature=0.4,
    )

    try:
        data = __import__("json").loads(spec)
    except Exception:
        # Fall back to the local heuristic planner if the LLM output is unusable
        data = codegen.plan_from_prompt(query)

    dag = Dag(query=query, label=data.get("name", "project"))
    for n in data.get("nodes", []):
        try:
            dag.add_node(
                TaskNode(
                    id=n["id"],
                    title=n["title"],
                    description=n["description"],
                    persona=n["persona"],
                    toolset=n.get("toolset", ["write_file"]),
                    depends_on=n.get("depends_on", []),
                )
            )
        except (KeyError, TypeError):
            continue
    for from_id, to_id in data.get("edges", []):
        try:
            dag.add_edge(from_id, to_id)
        except Exception:
            pass

    dag.validate()
    dag.created_at = time.time()
    await BUS.publish(
        "planner.finished",
        query=query,
        node_count=len(dag.nodes),
        edge_count=sum(len(n.depends_on) for n in dag.nodes.values()),
    )
    return dag
