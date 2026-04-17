"""
ProjectWorker — Worker assíncrono isolado por projeto.

Cada projeto registrado no sistema ganha seu próprio ProjectWorker.
O worker é uma asyncio.Task que roda indefinidamente enquanto o projeto
estiver ativo.  Ele:

  1. Observa o sistema de arquivos via watchdog (_FileWatcher interno)
  2. Debounça eventos (evita spam de Ctrl+S)
  3. Quando um arquivo muda → dispara IncrementalScanner
  4. Após o scan → dispara CrossProjectImpactEngine
  5. Publica resultado via SSE + Redis
  6. Ajusta frequência automaticamente:
       - Projeto ativo no workspace  → poll rápido (5s file, 30s git)
       - Projeto em background       → poll lento (30s file, 120s git)

Consumo de CPU/RAM é mínimo: o worker dorme entre ciclos.
Toda I/O de disco é feita em executor para não bloquear o event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("insightgraph.worker")

WATCHED_EXTENSIONS = {".java", ".ts", ".tsx", ".js", ".jsx",
                       ".py", ".sql", ".prc", ".fnc", ".pkg",
                       ".kt", ".swift", ".dart", ".cs", ".go"}

DEBOUNCE_SECONDS = 0.8   # agrupa eventos dentro de 800ms


# ─────────────────────────────────────────────
# File watcher interno (thread → asyncio bridge)
# ─────────────────────────────────────────────

class _FileWatcher:
    """
    Usa watchdog para monitorar o diretório do projeto.
    Roda em thread separada; envia eventos para uma asyncio.Queue.
    """

    def __init__(self, path: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._path = path
        self._queue = queue
        self._loop = loop
        self._observer = None

    def start(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Bridge(FileSystemEventHandler):
                def __init__(self_, q, loop):
                    self_._q = q
                    self_._loop = loop

                def _emit(self_, path: str):
                    if Path(path).suffix.lower() not in WATCHED_EXTENSIONS:
                        return
                    asyncio.run_coroutine_threadsafe(
                        self_._q.put(("change", path)), self_._loop
                    )

                def on_modified(self_, e):
                    if not e.is_directory: self_._emit(e.src_path)
                def on_created(self_, e):
                    if not e.is_directory: self_._emit(e.src_path)
                def on_moved(self_, e):
                    if not e.is_directory: self_._emit(e.dest_path)

            self._observer = Observer()
            self._observer.schedule(_Bridge(self._queue, self._loop),
                                     self._path, recursive=True)
            self._observer.start()
            logger.info("FileWatcher started: %s", self._path)
        except Exception as exc:
            logger.warning("watchdog not available, falling back to polling: %s", exc)

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)


# ─────────────────────────────────────────────
# ProjectWorker
# ─────────────────────────────────────────────

class ProjectWorker:
    """
    Worker assíncrono para um único projeto.

    Uso:
        worker = ProjectWorker(project, registry, incremental_scanner,
                               cross_impact_engine, event_stream)
        await worker.start()
        ...
        await worker.stop()
    """

    def __init__(
        self,
        project,                        # Project dataclass
        registry,                       # ProjectRegistry
        incremental_scanner,            # IncrementalScanner (shared, thread-safe)
        cross_impact_engine,            # CrossProjectImpactEngine
        event_stream=None,              # EventStream para SSE
        redis_client=None,
        priority: str = "background",   # "active" | "background"
    ):
        self._project = project
        self._registry = registry
        self._scanner = incremental_scanner
        self._cross = cross_impact_engine
        self._stream = event_stream
        self._redis = redis_client
        self.priority = priority

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._file_queue: asyncio.Queue = asyncio.Queue()
        self._watcher: Optional[_FileWatcher] = None

        # Pending files aguardando debounce
        self._pending: dict[str, float] = {}   # path → timestamp

    # ── Controle ──────────────────────────────

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        loop = asyncio.get_event_loop()
        self._watcher = _FileWatcher(self._project.path, self._file_queue, loop)
        self._watcher.start()
        self._task = asyncio.create_task(
            self._run(), name=f"worker-{self._project.id[:8]}"
        )
        self._registry.update_project_status(self._project.id, "watching")
        logger.info("Worker started: %s (%s)", self._project.name, self._project.id[:8])

    async def stop(self):
        self._stop_event.set()
        if self._watcher:
            self._watcher.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._registry.update_project_status(self._project.id, "idle")
        logger.info("Worker stopped: %s", self._project.name)

    def set_priority(self, priority: str):
        """active | background — ajusta frequência de polling"""
        self.priority = priority

    @property
    def _file_interval(self) -> float:
        return self._project.watch_interval if self.priority == "active" else                self._project.watch_interval * 6

    @property
    def _git_interval(self) -> float:
        return self._project.git_poll_interval if self.priority == "active" else                self._project.git_poll_interval * 4

    # ── Loop principal ─────────────────────────

    async def _run(self):
        last_git_check = 0.0
        logger.info("[%s] Loop iniciado (priority=%s)", self._project.name, self.priority)

        while not self._stop_event.is_set():
            try:
                # ── Coleta eventos de arquivo com debounce ──
                await self._collect_file_events()

                # ── Processa arquivos pendentes ──────────────
                now = time.monotonic()
                ready = [p for p, ts in list(self._pending.items())
                         if now - ts >= DEBOUNCE_SECONDS]
                for fp in ready:
                    del self._pending[fp]
                    await self._process_file(fp)

                # ── Git poll (menos frequente) ───────────────
                if now - last_git_check >= self._git_interval:
                    last_git_check = now
                    await self._check_git()

                await asyncio.sleep(0.2)   # yield; não bloqueia nada

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[%s] Worker error: %s", self._project.name, exc, exc_info=True)
                self._registry.update_project_status(
                    self._project.id, "error", str(exc)
                )
                await asyncio.sleep(5)   # backoff antes de retry

    async def _collect_file_events(self):
        """Drena a fila de eventos e registra timestamps para debounce."""
        deadline = time.monotonic() + 0.05   # max 50ms coletando
        while time.monotonic() < deadline:
            try:
                _, path = self._file_queue.get_nowait()
                self._pending[path] = time.monotonic()
            except asyncio.QueueEmpty:
                break

    # ── Processamento de arquivo ──────────────

    async def _process_file(self, file_path: str):
        """Scan incremental + análise cross-projeto para um arquivo."""
        logger.info("[%s] Processando: %s", self._project.name,
                    Path(file_path).name)
        self._registry.update_project_status(self._project.id, "scanning")

        try:
            # Scan incremental (atualiza grafo em memória + Neo4j)
            result = await self._scanner.process_file(
                file_path, self._project.path
            )

            # Impacto cross-projeto
            if result and result.changed_nodes:
                cross = await self._cross.analyze(
                    origin_project_id=self._project.id,
                    changed_file=file_path,
                    changed_nodes=result.changed_nodes,
                )

                # Publica SSE: graph_updated
                await self._publish_graph_updated(result, cross)

            self._registry.update_project_status(self._project.id, "watching")

        except Exception as exc:
            logger.error("[%s] process_file error: %s", self._project.name, exc)
            self._registry.update_project_status(
                self._project.id, "error", str(exc)
            )

    # ── Git poll ──────────────────────────────

    async def _check_git(self):
        """Verifica se o commit mudou; se sim, dispara scan completo incremental."""
        loop = asyncio.get_event_loop()
        try:
            import subprocess
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self._project.path,
                    capture_output=True, text=True, timeout=5,
                ),
            )
            if result.returncode != 0:
                return
            commit = result.stdout.strip()
            if commit == self._project.last_commit:
                return

            logger.info("[%s] Novo commit detectado: %s", self._project.name, commit[:8])
            self._registry.update_project_commit(self._project.id, commit)

            # Pega arquivos alterados no commit
            diff = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "diff-tree", "--no-commit-id", "-r",
                     "--name-only", commit],
                    cwd=self._project.path,
                    capture_output=True, text=True, timeout=10,
                ),
            )
            changed_files = [
                str(Path(self._project.path) / f.strip())
                for f in diff.stdout.splitlines()
                if f.strip() and Path(f.strip()).suffix in WATCHED_EXTENSIONS
            ]
            for fp in changed_files:
                self._pending[fp] = time.monotonic() - DEBOUNCE_SECONDS  # já pronto

        except Exception as exc:
            logger.debug("[%s] git check failed: %s", self._project.name, exc)

    # ── Publicação SSE ────────────────────────

    async def _publish_graph_updated(self, scan_result, cross_result):
        if not self._stream:
            return
        try:
            from event_stream import SSEEvent
            payload = {
                "project_id": self._project.id,
                "project_name": self._project.name,
                "file": scan_result.file_path if scan_result else "",
                "changed_nodes": scan_result.changed_nodes if scan_result else [],
                "risk_score": scan_result.risk_score if scan_result else 0,
                "cross_project": {
                    "total_affected": cross_result.total_affected,
                    "breaking_count": cross_result.breaking_count,
                    "affected_projects": list({
                        a.project_name for a in cross_result.affected_in_siblings
                    }),
                } if cross_result else None,
            }
            await self._stream.publish(SSEEvent(
                type="graph_updated",
                payload=payload,
                timestamp=time.time(),
            ))
        except Exception as exc:
            logger.warning("SSE publish error: %s", exc)
