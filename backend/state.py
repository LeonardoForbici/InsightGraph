from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel


class ScanStatusModel(BaseModel):
    status: str = "idle"
    scanned_files: int = 0
    total_files: int = 0
    total_nodes: int = 0
    total_relationships: int = 0
    progress_percent: float = 0.0
    current_file: str = ""
    errors: list[str] = []


class AppState:
    _instance: Optional["AppState"] = None

    def __init__(self):
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.rag_index: list[dict] = []
        self.rag_index_metadata: dict = {}
        self.scanned_projects: dict[str, str] = {}
        self.todos: list[dict] = []
        self.scan_status = ScanStatusModel()

        self.scan_lock = asyncio.Lock()
        self.ai_semaphore = asyncio.Semaphore(1)

    @classmethod
    def instance(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        return None

    def clear_graph(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.rag_index.clear()
        self.rag_index_metadata.clear()

    def get_node(self, key: str) -> Optional[dict]:
        return self.nodes.get(key)

    def add_nodes(self, nodes: list[dict]) -> None:
        self.nodes.extend(nodes)
