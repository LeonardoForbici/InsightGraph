"""
Git Service - Análise de Code Churn
Utiliza PyDriller para calcular churn rate dos últimos 6 meses
Operações assíncronas para não bloquear FastAPI
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict
import os

logger = logging.getLogger("insightgraph.git_service")

try:
    from pydriller import Repository
except ImportError:
    logger.warning("PyDriller not installed. Install with: pip install PyDriller")
    Repository = None


class ChurnMetrics:
    """Armazena métricas de churn para um ficheiro"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.commit_count = 0
        self.total_lines_added = 0
        self.total_lines_removed = 0
        self.last_modified = None
        self.churn_rate = 0.0  # Commits por mês
        self.churn_intensity = 0.0  # Linhas alteradas por commit
    
    def calculate_metrics(self, months: int = 6):
        """Calcula métricas finalizadas"""
        if self.commit_count == 0:
            self.churn_rate = 0.0
            self.churn_intensity = 0.0
            return
        
        # Churn rate: commits por mês
        self.churn_rate = self.commit_count / max(months, 1)
        
        # Intensidade: linhas alteradas por commit
        total_changes = self.total_lines_added + self.total_lines_removed
        self.churn_intensity = total_changes / max(self.commit_count, 1)


class GitService:
    """Serviço de análise Git com operações assíncronas"""
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.metrics: Dict[str, ChurnMetrics] = {}
        self._cache_expiry = None
    
    async def analyze_churn_async(self, months: int = 6) -> Dict[str, ChurnMetrics]:
        """
        Análise de churn em thread separada (non-blocking).
        
        Args:
            months: Número de meses a analisar (default 6)
        
        Returns:
            Dict mapeando file_path -> ChurnMetrics
        """
        # Executar em executor thread pool para não bloquear event loop
        loop = asyncio.get_event_loop()
        metrics = await loop.run_in_executor(
            None,
            self._analyze_churn_sync,
            months
        )
        return metrics
    
    def _analyze_churn_sync(self, months: int = 6) -> Dict[str, ChurnMetrics]:
        """
        Análise síncrona de churn (executada em thread pool).
        """
        if not Repository:
            logger.error("PyDriller não disponível")
            return {}
        
        if not os.path.isdir(self.repo_path):
            logger.error(f"Repositório não encontrado: {self.repo_path}")
            return {}
        
        metrics = defaultdict(lambda: ChurnMetrics(""))
        since_date = datetime.now() - timedelta(days=30 * months)
        
        try:
            repo = Repository(self.repo_path, since=since_date)
            
            for commit in repo.traverse_commits():
                for file in commit.files:
                    # Normalizar path
                    file_path = file.new_path if file.new_path else file.old_path
                    if not file_path:
                        continue
                    
                    if file_path not in metrics:
                        metrics[file_path] = ChurnMetrics(file_path)
                    
                    m = metrics[file_path]
                    m.commit_count += 1
                    m.total_lines_added += file.additions if file.additions else 0
                    m.total_lines_removed += file.deletions if file.deletions else 0
                    m.last_modified = commit.committer_date
        
        except Exception as e:
            logger.error(f"Erro ao analisar repositório Git: {e}")
            return {}
        
        # Finalizar cálculos
        result = {}
        for file_path, metrics_obj in metrics.items():
            metrics_obj.calculate_metrics(months)
            result[file_path] = metrics_obj
        
        return result
    
    def map_git_metrics_to_graph(self, churn_metrics: Dict[str, ChurnMetrics], 
                                 project_path: str) -> Dict[str, Dict]:
        """
        Mapeia métricas Git para namespace_keys do grafo.
        
        Converte file_path absoluto para relative (como no parser).
        Retorna dict: namespace_key -> {"churn_rate": float, "churn_intensity": float}
        """
        mapping = {}
        
        for file_path_abs, metrics in churn_metrics.items():
            try:
                # Relativizar path
                rel_path = os.path.relpath(file_path_abs, project_path).replace("\\", "/")
                
                # Extrair extensão e tipo de ficheiro
                ext = Path(file_path_abs).suffix.lower()
                
                # Para mapear para namespace_key, precisamos conhecer o project_name
                # Exemplo: project_path = "/home/user/MyApp"
                # namespace_key seria: "MyApp:src/main/java/User.java:UserClass"
                # Armazenamos no file_path nivel: "project_name:rel_path"
                
                project_name = Path(project_path).name
                file_key = f"{project_name}:{rel_path}"
                
                mapping[file_key] = {
                    "churn_rate": metrics.churn_rate,
                    "churn_intensity": metrics.churn_intensity,
                    "commit_count": metrics.commit_count,
                    "lines_added": metrics.total_lines_added,
                    "lines_removed": metrics.total_lines_removed,
                }
            except Exception as e:
                logger.warning(f"Erro ao mapear {file_path_abs}: {e}")
                continue
        
        return mapping


# ──────────────────────────────────────────────
# True Risk Score Calculator
# ──────────────────────────────────────────────

class RiskScoreCalculator:
    """Combina Complexidade Ciclomática + Churn para calcular True Risk Score"""
    
    @staticmethod
    def calculate_true_risk(complexity: int, churn_rate: float, churn_intensity: float) -> Tuple[float, str]:
        """
        Formula: True_Risk_Score = (Complexity * 2) + (Churn_Rate * 1.5) + (Churn_Intensity * 0.5)
        
        Rationale:
        - Complexidade é o maior factor (code é difícil de mudar corretamente)
        - Churn_Rate (commits/mês) indica mudanças frequentes = risco de bugs
        - Churn_Intensity (linhas/commit) indica mudanças grandes = maior risco
        
        Returns:
            (score: float, severity: str)
            Severity: "Low" (< 30), "Medium" (30-60), "High" (60-90), "Critical" (> 90)
        """
        
        # Normalizar churn_rate e churn_intensity para escala 0-100
        # Assumir: churn_rate > 5 commits/mês é "alto"
        # Assumir: churn_intensity > 50 linhas/commit é "alto"
        normalized_churn_rate = min(100, churn_rate * 20)
        normalized_churn_intensity = min(100, churn_intensity / 0.5)  # Max 50 linhas/commit -> 100
        
        complexity_factor = min(100, complexity * 2)  # Max 50 complexity -> 100
        
        true_risk = (complexity_factor * 0.50) + (normalized_churn_rate * 0.35) + (normalized_churn_intensity * 0.15)
        
        if true_risk < 30:
            severity = "Low"
        elif true_risk < 60:
            severity = "Medium"
        elif true_risk < 90:
            severity = "High"
        else:
            severity = "Critical"
        
        return true_risk, severity
    
    @staticmethod
    def get_hotspot_color(true_risk_score: float) -> Dict[str, str]:
        """Retorna cor para visualização no frontend baseada no risk score"""
        if true_risk_score < 30:
            return {"color": "#22c55e", "label": "Low Risk"}  # Verde
        elif true_risk_score < 60:
            return {"color": "#eab308", "label": "Medium Risk"}  # Amarelo
        elif true_risk_score < 90:
            return {"color": "#f97316", "label": "High Risk"}  # Laranja
        else:
            return {"color": "#ef4444", "label": "Critical Risk"}  # Vermelho


# ──────────────────────────────────────────────
# Background Task para Scan Git
# ──────────────────────────────────────────────

async def analyze_and_update_git_churn(project_path: str, neo4j_service) -> Dict:
    """
    Task assíncrona para analisar Git e atualizar Neo4j com churn metrics.
    Deve ser chamada como background task no FastAPI.
    
    Exemplo de uso:
    ```python
    from fastapi import BackgroundTasks
    
    @app.post("/api/scan")
    async def scan_project(paths: list[str], background_tasks: BackgroundTasks):
        # ... scan code ...
        for path in paths:
            background_tasks.add_task(analyze_and_update_git_churn, path, neo4j_service)
    ```
    """
    logger.info(f"Background task iniciada para Git churn: {project_path}")
    
    try:
        git_service = GitService(project_path)
        churn_metrics = await git_service.analyze_churn_async(months=6)
        
        file_mapping = git_service.map_git_metrics_to_graph(churn_metrics, project_path)
        
        # Atualizar Neo4j
        for file_key, metrics in file_mapping.items():
            true_risk, severity = RiskScoreCalculator.calculate_true_risk(
                10,  # Default complexity - será sobrescrito se existir
                metrics["churn_rate"],
                metrics["churn_intensity"]
            )
            
            # Query: Encontrar nós deste ficheiro e atualizar
            query = """
            MATCH (n:Entity)
            WHERE n.file CONTAINS $file_key OR n.namespace_key CONTAINS $file_key
            SET n.churn_rate = $churn_rate,
                n.churn_intensity = $churn_intensity,
                n.commit_count = $commit_count,
                n.git_analyzed_at = datetime()
            """
            
            try:
                neo4j_service.graph.run(query, 
                    file_key=file_key,
                    churn_rate=metrics["churn_rate"],
                    churn_intensity=metrics["churn_intensity"],
                    commit_count=metrics["commit_count"]
                )
            except Exception as e:
                logger.error(f"Erro ao atualizar Neo4j para {file_key}: {e}")
        
        logger.info(f"Git churn analysis concluído para {project_path}")
        return {"status": "completed", "files_analyzed": len(file_mapping)}
    
    except Exception as e:
        logger.error(f"Erro no background task de Git churn: {e}")
        return {"status": "error", "error": str(e)}
