"""Run workspace: materializes agent artifacts on disk under workspaces/<run_id>/."""
from __future__ import annotations

import os
from pathlib import Path

from .events import BUS

ROOT = Path(__file__).resolve().parent.parent / "workspaces"


class Workspace:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.dir = ROOT / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    async def write(self, rel_path: str, content: str) -> str:
        path = self.dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        await BUS.publish(
            "artifact.created",
            run_id=self.run_id,
            path=rel_path,
            size=len(content),
        )
        return rel_path

    def read(self, rel_path: str) -> str:
        return (self.dir / rel_path).read_text(encoding="utf-8")

    def list_files(self) -> list[dict]:
        out = []
        for p in sorted(self.dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(self.dir).as_posix()
                out.append({"path": rel, "size": p.stat().st_size})
        return out

    def tree(self) -> str:
        lines = [f"{self.run_id}/"]
        for f in self.list_files():
            lines.append(f"  {f['path']}  ({f['size']} bytes)")
        return "\n".join(lines)
