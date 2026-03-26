import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class RagEntry:
    node_key: str
    summary: str
    model: Optional[str]
    updated_at: float
    embedding: Optional[np.ndarray]
    norm: float


class RagStore:
    """Persistent SQLite-backed RAG store with an LRU query cache."""

    def __init__(self, db_path: Path | str, cache_size: int = 1000):
        self.db_path = Path(db_path)
        self.cache_size = cache_size
        self._lock = threading.Lock()
        self._initialized = False
        self.entries: list[RagEntry] = []
        self._cache: OrderedDict[Tuple[str, str], list[RagEntry]] = OrderedDict()

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS node_embeddings (
                        node_key TEXT PRIMARY KEY,
                        summary TEXT,
                        embedding BLOB,
                        model TEXT,
                        updated_at REAL
                    )
                    """
                )
            self._initialized = True
        self.load_entries()

    def _serialize(self, vector: Iterable[float] | None) -> Optional[bytes]:
        if vector is None:
            return None
        arr = np.asarray(list(vector), dtype=np.float32)
        if arr.size == 0:
            return None
        return arr.tobytes()

    def _deserialize(self, blob: bytes | None) -> Optional[np.ndarray]:
        if not blob:
            return None
        arr = np.frombuffer(blob, dtype=np.float32)
        if arr.size == 0:
            return None
        return arr

    def load_entries(self) -> None:
        with self._lock:
            if not self._initialized:
                self.initialize()
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT node_key, summary, embedding, model, updated_at FROM node_embeddings"
                ).fetchall()
            entries: list[RagEntry] = []
            for row in rows:
                embedding = self._deserialize(row[2])
                norm = float(np.linalg.norm(embedding)) if embedding is not None else 0.0
                entries.append(
                    RagEntry(
                        node_key=row[0],
                        summary=row[1] or "",
                        model=row[3],
                        updated_at=row[4] or time.time(),
                        embedding=embedding,
                        norm=norm,
                    )
                )
            entries.sort(key=lambda entry: entry.updated_at, reverse=True)
            self.entries = entries
            self._cache.clear()

    def upsert(self, node_key: str, summary: str, embedding: Optional[Iterable[float]], model: Optional[str]) -> None:
        blob = self._serialize(embedding)
        now = time.time()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO node_embeddings(node_key, summary, embedding, model, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(node_key) DO UPDATE SET
                        summary = excluded.summary,
                        embedding = excluded.embedding,
                        model = excluded.model,
                        updated_at = excluded.updated_at
                    """,
                    (node_key, summary, blob, model, now),
                )
                conn.commit()
            embedding_arr = self._deserialize(blob)
            entry = RagEntry(
                node_key=node_key,
                summary=summary,
                model=model,
                updated_at=now,
                embedding=embedding_arr,
                norm=float(np.linalg.norm(embedding_arr)) if embedding_arr is not None else 0.0,
            )
            self.entries = [e for e in self.entries if e.node_key != node_key]
            self.entries.insert(0, entry)
            self._cache.clear()

    def _cache_lookup(self, key: Tuple[str, str]) -> Optional[list[RagEntry]]:
        with self._lock:
            value = self._cache.pop(key, None)
            if value is not None:
                self._cache[key] = value
            return value

    def _cache_store(self, key: Tuple[str, str], value: list[RagEntry]) -> None:
        with self._lock:
            self._cache[key] = value
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    def query(
        self,
        query_embedding: Optional[Iterable[float]],
        query_text: str,
        limit: int = 20,
        threshold: float = 0.65,
    ) -> list[dict[str, Any]]:
        key = (query_text.strip().lower(), str(limit))
        cached = self._cache_lookup(key)
        if cached is not None:
            return [self._entry_to_dict(entry) for entry in cached[:limit]]

        if query_embedding is None:
            results = self.entries[:limit]
            self._cache_store(key, results)
            return [self._entry_to_dict(entry) for entry in results]

        query_arr = np.asarray(list(query_embedding), dtype=np.float32)
        if query_arr.size == 0:
            return []
        query_norm = float(np.linalg.norm(query_arr)) or 1.0
        scored: list[Tuple[float, RagEntry]] = []
        for entry in self.entries:
            if entry.embedding is None or entry.norm == 0.0:
                continue
            score = float(np.dot(query_arr, entry.embedding) / (query_norm * entry.norm))
            if score >= threshold:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = [entry for _, entry in scored[:limit]]
        self._cache_store(key, results)
        return [self._entry_to_dict(entry, score) for entry in results]

    @staticmethod
    def _entry_to_dict(entry: RagEntry, score: float | None = None) -> dict[str, Any]:
        result = {
            "node_key": entry.node_key,
            "summary": entry.summary,
            "model": entry.model,
            "updated_at": entry.updated_at,
        }
        if score is not None:
            result["score"] = score
        return result

    def clear(self) -> None:
        with self._lock:
            self.entries.clear()
            self._cache.clear()
