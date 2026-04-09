"""
WatchManager — Monitora diretórios e dispara scan incremental.

Usa watchfiles (async file watcher) para detectar mudanças e chamar
IncrementalScanner.process_file() para cada arquivo modificado.

Requirements: Task 4 (Watch Mode)
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional

from watchfiles import awatch, Change

logger = logging.getLogger("insightgraph.watch")

# Extensões monitoradas
WATCHED_EXTENSIONS = {".java", ".ts", ".tsx", ".sql", ".prc", ".fnc", ".pkg"}

# Diretórios ignorados
IGNORED_DIRS = {"node_modules", ".git", "target", "build", "dist", ".gradle", "__pycache__", ".venv", "venv"}


class WatchManager:
    """
    Gerencia monitoramento de múltiplos projetos simultaneamente.
    
    Para cada projeto monitorado:
    - Usa watchfiles.awatch() de forma assíncrona
    - Filtra apenas arquivos relevantes
    - Ignora diretórios de build/dependências
    - Chama callback para cada arquivo modificado
    - Thread-safe via asyncio.Lock
    """

    def __init__(self, on_file_changed: Optional[Callable[[str, str], None]] = None):
        """
        Args:
            on_file_changed: Callback async (file_path, project_path) -> None
        """
        self._on_file_changed = on_file_changed
        self._watching: dict[str, asyncio.Task] = {}  # project_path -> watch task
        self._lock = asyncio.Lock()

    async def start(self, project_path: str) -> None:
        """
        Inicia monitoramento de um projeto.
        
        Args:
            project_path: Caminho absoluto do diretório raiz do projeto
        """
        async with self._lock:
            if project_path in self._watching:
                logger.warning("Projeto já está sendo monitorado: %s", project_path)
                return
            
            path = Path(project_path).resolve()
            if not path.exists() or not path.is_dir():
                raise ValueError(f"Caminho inválido: {project_path}")
            
            # Criar task de monitoramento
            task = asyncio.create_task(self._watch_project(str(path)))
            self._watching[str(path)] = task
            
            logger.info("Monitoramento iniciado: %s", path)

    async def stop(self, project_path: str) -> None:
        """
        Para monitoramento de um projeto.
        
        Args:
            project_path: Caminho do projeto a parar
        """
        async with self._lock:
            path = str(Path(project_path).resolve())
            
            if path not in self._watching:
                logger.warning("Projeto não está sendo monitorado: %s", path)
                return
            
            # Cancelar task
            task = self._watching.pop(path)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            logger.info("Monitoramento parado: %s", path)

    def is_watching(self, project_path: str) -> bool:
        """Verifica se um projeto está sendo monitorado."""
        path = str(Path(project_path).resolve())
        return path in self._watching

    def list_watching(self) -> list[str]:
        """Lista todos os projetos sendo monitorados."""
        return list(self._watching.keys())

    async def stop_all(self) -> None:
        """Para monitoramento de todos os projetos."""
        paths = list(self._watching.keys())
        for path in paths:
            await self.stop(path)

    async def _watch_project(self, project_path: str) -> None:
        """
        Loop de monitoramento para um projeto específico.
        
        Usa watchfiles.awatch() para detectar mudanças e filtrar eventos relevantes.
        """
        logger.info("Iniciando watch loop para: %s", project_path)
        
        try:
            async for changes in awatch(project_path, stop_event=None):
                for change_type, file_path in changes:
                    # Filtrar eventos relevantes
                    if not self._should_process(file_path, project_path):
                        continue
                    
                    # Log do evento
                    change_name = self._change_type_name(change_type)
                    logger.debug("Arquivo %s: %s", change_name, file_path)
                    
                    # Chamar callback
                    if self._on_file_changed:
                        try:
                            await self._on_file_changed(file_path, project_path)
                        except Exception as e:
                            logger.error(
                                "Erro ao processar arquivo %s: %s",
                                file_path,
                                e,
                                exc_info=True,
                            )
        
        except asyncio.CancelledError:
            logger.info("Watch loop cancelado para: %s", project_path)
            raise
        except Exception as e:
            logger.error("Erro no watch loop de %s: %s", project_path, e, exc_info=True)

    def _should_process(self, file_path: str, project_path: str) -> bool:
        """
        Verifica se um arquivo deve ser processado.
        
        Filtra por:
        - Extensão do arquivo
        - Diretórios ignorados
        """
        path = Path(file_path)
        
        # Verificar extensão
        if path.suffix.lower() not in WATCHED_EXTENSIONS:
            return False
        
        # Verificar se está em diretório ignorado
        try:
            rel_path = path.relative_to(project_path)
            for part in rel_path.parts:
                if part in IGNORED_DIRS:
                    return False
        except ValueError:
            # Arquivo fora do projeto
            return False
        
        return True

    def _change_type_name(self, change_type: Change) -> str:
        """Converte enum Change para string legível."""
        if change_type == Change.added:
            return "criado"
        if change_type == Change.modified:
            return "modificado"
        if change_type == Change.deleted:
            return "deletado"
        return "alterado"
