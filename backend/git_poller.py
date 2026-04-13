"""
GitPoller — Fase de Automação: detecção automática de commits e scan contínuo.

Roda um loop assíncrono que verifica git rev-parse HEAD a cada N segundos.
Se o commit mudou → dispara scan incremental automaticamente.

Inicializado no lifespan do FastAPI; sobrevive a restarts via persistência em SQLite.
"""

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("insightgraph.git_poller")


class GitPoller:
    """
    Monitora um repositório git e dispara scans automaticamente a cada novo commit.
    """

    def __init__(
        self,
        project_path: Optional[str] = None,
        interval_seconds: int = 60,
        state_store=None,
        scan_callback=None,
    ):
        """
        Args:
            project_path: Caminho do repo git a monitorar. Se None, detecta via git rev-parse --show-toplevel.
            interval_seconds: Segundos entre checagens (default: 60).
            state_store: LocalStateStore para persistir último commit visto.
            scan_callback: Função assíncrona async (paths, commit_hash) chamada quando commit muda.
        """
        self._project_path = self._resolve_project_path(project_path)
        self._interval = interval_seconds
        self._store = state_store
        self._scan_callback = scan_callback
        self._running = False
        self._last_commit: Optional[str] = None

    def _resolve_project_path(self, path: Optional[str]) -> Path:
        """Resolve o caminho raiz do git repo."""
        if path:
            start = Path(path).resolve()
        else:
            start = Path.cwd()

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=start,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return Path(result.stdout.strip())
        except Exception:
            pass
        return start

    def _get_current_commit(self) -> Optional[str]:
        """Retorna o hash do commit atual. Returns None se não é um repo git."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as exc:
            logger.debug("Could not get current commit: %s", exc)
        return None

    def _load_last_seen_commit(self) -> Optional[str]:
        """Carrega o último commit visto do state_store."""
        if not self._store:
            return None
        try:
            return self._store.get_state("poller_last_commit")
        except Exception:
            return None

    def _save_last_seen_commit(self, commit_hash: str) -> None:
        """Persiste o último commit visto no state_store."""
        if not self._store:
            return
        try:
            self._store.set_state("poller_last_commit", commit_hash)
        except Exception as exc:
            logger.warning("Failed to persist commit: %s", exc)

    def _get_last_scan_time(self) -> Optional[float]:
        """Retorna timestamp do último scan."""
        if not self._store:
            return None
        try:
            return self._store.get_state("poller_last_scan_at")
        except Exception:
            return None

    def _save_last_scan_time(self, ts: float) -> None:
        """Persiste timestamp do último scan."""
        if not self._store:
            return
        try:
            self._store.set_state("poller_last_scan_at", ts)
        except Exception as exc:
            logger.warning("Failed to persist scan time: %s", exc)

    async def run(self) -> None:
        """Inicia o loop de monitoramento."""
        self._running = True
        self._last_commit = self._load_last_seen_commit()

        logger.info(
            "GitPoller started: monitoring %s, interval=%ds, last_commit=%s",
            self._project_path,
            self._interval,
            self._last_commit or "—",
        )

        while self._running:
            try:
                await asyncio.sleep(self._interval)
                current_commit = self._get_current_commit()

                if not current_commit:
                    logger.debug("Not in a git repository")
                    continue

                if current_commit != self._last_commit:
                    logger.info(
                        "New commit detected: %s (was %s)",
                        current_commit[:8],
                        self._last_commit[:8] if self._last_commit else "—",
                    )

                    # Disparar scan
                    if self._scan_callback:
                        try:
                            await self._scan_callback([str(self._project_path)], current_commit)
                            self._save_last_scan_time(time.time())
                        except Exception as exc:
                            logger.error("Scan callback failed: %s", exc)

                    # Persistir novo commit
                    self._last_commit = current_commit
                    self._save_last_seen_commit(current_commit)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("GitPoller error: %s", exc)

        self._running = False
        logger.info("GitPoller stopped")

    def stop(self) -> None:
        """Para o loop."""
        self._running = False

    def get_status(self) -> dict:
        """Retorna status atual do poller."""
        return {
            "active": self._running,
            "project_path": str(self._project_path),
            "last_commit": self._last_commit,
            "last_commit_short": self._last_commit[:8] if self._last_commit else None,
            "last_scan_at": self._get_last_scan_time(),
            "interval_seconds": self._interval,
        }
