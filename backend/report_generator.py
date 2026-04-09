"""
Report Generator — Task 13

Generates executive PDF reports with:
- Current graph metrics
- Historical snapshots and trends
- Audit alerts
- AI-generated executive summary
"""

import os
import logging
import datetime
from pathlib import Path
from typing import Any
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
import httpx

logger = logging.getLogger("insightgraph.report_generator")


class ReportGenerator:
    """Generate executive PDF reports from graph data and analysis history."""

    def __init__(
        self,
        neo4j_service,
        state_store,
        temporal_analyzer,
        audit_job,
        ollama_url: str,
        ollama_chat_model: str,
        templates_dir: Path,
        reports_output_dir: Path,
    ):
        self.neo4j_service = neo4j_service
        self.state_store = state_store
        self.temporal_analyzer = temporal_analyzer
        self.audit_job = audit_job
        self.ollama_url = ollama_url
        self.ollama_chat_model = ollama_chat_model
        self.templates_dir = templates_dir
        self.reports_output_dir = reports_output_dir
        self.reports_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup Jinja2 environment
        self.jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))

    async def generate_report(self, project: str | None = None, tenant: str | None = None) -> dict:
        """
        Generate an executive PDF report.
        
        Tasks 13.3, 13.4, 13.5, 13.9
        
        Returns:
            dict with keys: report_id, filename, file_path, file_size
        """
        logger.info(f"Generating executive report (project={project}, tenant={tenant})")
        
        # Task 13.3 — Collect data
        data = await self._collect_data(project=project, tenant=tenant)
        
        # Task 13.4 — Generate executive summary
        executive_summary = await self._generate_executive_summary(data)
        data["executive_summary"] = executive_summary
        
        # Task 13.5 — Render HTML and convert to PDF
        html_content = self._render_html(data)
        pdf_path = self._generate_pdf(html_content, project=project)
        
        # Save to report history
        file_size = pdf_path.stat().st_size
        report_record = self.state_store.save_report(
            filename=pdf_path.name,
            file_path=str(pdf_path),
            file_size=file_size,
            project=project,
        )
        
        logger.info(f"Report generated: {pdf_path.name} ({file_size} bytes)")
        return report_record

    async def _collect_data(self, project: str | None = None, tenant: str | None = None) -> dict[str, Any]:
        """
        Task 13.3 — Collect graph data, snapshots, and audit alerts.
        Task 13.9 — Handle case with no historical snapshots.
        """
        data: dict[str, Any] = {
            "generated_at": datetime.datetime.now().isoformat(),
            "project": project or "All Projects",
            "tenant": tenant,
        }
        
        # Current graph stats
        if self.neo4j_service.is_connected:
            try:
                stats = self.neo4j_service.get_stats(tenant=tenant)
                data["current_stats"] = stats
            except Exception as e:
                logger.warning(f"Failed to get graph stats: {e}")
                data["current_stats"] = self._empty_stats()
        else:
            data["current_stats"] = self._empty_stats()
        
        # Filter by project if specified
        if project and data["current_stats"].get("projects"):
            if project not in data["current_stats"]["projects"]:
                logger.warning(f"Project '{project}' not found in graph")
        
        # Historical snapshots (Task 13.9 — handle no snapshots case)
        try:
            history = self.temporal_analyzer.get_history(page=1, limit=10)
            data["snapshots"] = history.get("items", [])
            data["has_snapshots"] = len(data["snapshots"]) > 0
            
            # Calculate trend if we have at least 2 snapshots
            if len(data["snapshots"]) >= 2:
                latest = data["snapshots"][0]
                oldest = data["snapshots"][-1]
                data["trend"] = self._calculate_trend(oldest, latest)
            else:
                data["trend"] = None
        except Exception as e:
            logger.warning(f"Failed to get snapshots: {e}")
            data["snapshots"] = []
            data["has_snapshots"] = False
            data["trend"] = None
        
        # Audit alerts
        try:
            alerts_response = self.audit_job.get_alerts()
            data["audit_alerts"] = alerts_response.get("items", [])
            data["critical_alerts"] = [
                a for a in data["audit_alerts"]
                if a.get("severity") in ("high", "critical")
            ]
        except Exception as e:
            logger.warning(f"Failed to get audit alerts: {e}")
            data["audit_alerts"] = []
            data["critical_alerts"] = []
        
        # Top hotspots (nodes with highest risk)
        data["top_hotspots"] = self._get_top_hotspots(project=project, tenant=tenant, limit=10)
        
        return data

    async def _generate_executive_summary(self, data: dict) -> str:
        """
        Task 13.4 — Generate executive summary in non-technical language using Ollama.
        """
        # Build context for AI
        stats = data.get("current_stats", {})
        alerts = data.get("critical_alerts", [])
        trend = data.get("trend")
        has_snapshots = data.get("has_snapshots", False)
        
        context_parts = [
            f"Sistema com {stats.get('total_nodes', 0)} componentes e {stats.get('total_edges', 0)} dependências.",
        ]
        
        if has_snapshots and trend:
            if trend.get("nodes_change", 0) > 0:
                context_parts.append(f"O sistema cresceu {trend['nodes_change']} componentes desde a última análise.")
            elif trend.get("nodes_change", 0) < 0:
                context_parts.append(f"O sistema reduziu {abs(trend['nodes_change'])} componentes desde a última análise.")
            
            if trend.get("complexity_trend") == "increasing":
                context_parts.append("A complexidade do código está aumentando.")
            elif trend.get("complexity_trend") == "decreasing":
                context_parts.append("A complexidade do código está diminuindo.")
        
        if len(alerts) > 0:
            context_parts.append(f"Existem {len(alerts)} alertas críticos que requerem atenção imediata.")
        else:
            context_parts.append("Não há alertas críticos no momento.")
        
        context = " ".join(context_parts)
        
        # Generate summary using Ollama
        prompt = f"""Você é um consultor técnico escrevendo um resumo executivo para gestores não-técnicos.

Contexto do sistema:
{context}

Escreva um parágrafo executivo (máximo 150 palavras) em linguagem não técnica que:
1. Resuma o estado atual do sistema
2. Destaque os principais riscos (se houver)
3. Indique se a situação está melhorando ou piorando
4. Seja objetivo e direto

Resumo executivo:"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_chat_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 200,
                        }
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    summary = result.get("response", "").strip()
                    logger.info("Executive summary generated successfully")
                    return summary
                else:
                    logger.warning(f"Ollama request failed: {response.status_code}")
                    return self._fallback_summary(data)
        except Exception as e:
            logger.error(f"Failed to generate AI summary: {e}")
            return self._fallback_summary(data)

    def _fallback_summary(self, data: dict) -> str:
        """Generate a simple summary when AI is unavailable."""
        stats = data.get("current_stats", {})
        alerts = data.get("critical_alerts", [])
        
        summary = f"O sistema possui {stats.get('total_nodes', 0)} componentes distribuídos em {len(stats.get('projects', []))} projeto(s). "
        
        if len(alerts) > 0:
            summary += f"Foram identificados {len(alerts)} alertas críticos que requerem atenção da equipe técnica. "
        else:
            summary += "O sistema está operando dentro dos parâmetros esperados. "
        
        if not data.get("has_snapshots"):
            summary += "Este é o primeiro relatório gerado, portanto não há dados históricos para comparação."
        
        return summary

    def _render_html(self, data: dict) -> str:
        """Task 13.5 — Render HTML template with data."""
        template = self.jinja_env.get_template("report_base.html")
        
        # Add helper functions for template
        data["format_number"] = lambda n: f"{n:,}".replace(",", ".")
        data["format_date"] = lambda ts: datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
        
        html_content = template.render(**data)
        return html_content

    def _generate_pdf(self, html_content: str, project: str | None = None) -> Path:
        """Task 13.5 — Convert HTML to PDF using weasyprint."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_suffix = f"_{project}" if project else ""
        filename = f"insightgraph-report{project_suffix}_{timestamp}.pdf"
        pdf_path = self.reports_output_dir / filename
        
        # Convert HTML to PDF
        HTML(string=html_content).write_pdf(
            pdf_path,
            stylesheets=[CSS(string=self._get_pdf_styles())]
        )
        
        return pdf_path

    def _get_pdf_styles(self) -> str:
        """Additional CSS styles for PDF generation."""
        return """
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }
        h1 {
            color: #2563eb;
            font-size: 24pt;
            margin-bottom: 0.5cm;
        }
        h2 {
            color: #1e40af;
            font-size: 18pt;
            margin-top: 1cm;
            margin-bottom: 0.3cm;
            border-bottom: 2px solid #3b82f6;
            padding-bottom: 0.2cm;
        }
        h3 {
            color: #1e3a8a;
            font-size: 14pt;
            margin-top: 0.5cm;
            margin-bottom: 0.3cm;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 0.5cm 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f3f4f6;
            font-weight: bold;
        }
        .metric {
            background-color: #eff6ff;
            padding: 0.3cm;
            margin: 0.3cm 0;
            border-left: 4px solid #3b82f6;
        }
        .alert-critical {
            background-color: #fee2e2;
            border-left: 4px solid #dc2626;
            padding: 0.3cm;
            margin: 0.3cm 0;
        }
        .alert-high {
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 0.3cm;
            margin: 0.3cm 0;
        }
        .no-data {
            color: #6b7280;
            font-style: italic;
            padding: 0.5cm;
            text-align: center;
        }
        """

    def _empty_stats(self) -> dict:
        """Return empty stats structure."""
        return {
            "total_nodes": 0,
            "total_edges": 0,
            "nodes_by_type": {},
            "edges_by_type": {},
            "layers": {},
            "projects": [],
        }

    def _calculate_trend(self, old_snapshot: dict, new_snapshot: dict) -> dict:
        """Calculate trend between two snapshots."""
        return {
            "nodes_change": new_snapshot.get("total_nodes", 0) - old_snapshot.get("total_nodes", 0),
            "edges_change": new_snapshot.get("total_edges", 0) - old_snapshot.get("total_edges", 0),
            "god_classes_change": new_snapshot.get("god_classes", 0) - old_snapshot.get("god_classes", 0),
            "complexity_trend": "increasing" if new_snapshot.get("god_classes", 0) > old_snapshot.get("god_classes", 0) else "decreasing" if new_snapshot.get("god_classes", 0) < old_snapshot.get("god_classes", 0) else "stable",
        }

    def _get_top_hotspots(self, project: str | None = None, tenant: str | None = None, limit: int = 10) -> list[dict]:
        """Get top hotspot nodes (high complexity, high coupling)."""
        if not self.neo4j_service.is_connected:
            return []
        
        try:
            tenant_filter = "WHERE n.tenant = $tenant" if tenant else ""
            params = {"tenant": tenant, "limit": limit} if tenant else {"limit": limit}
            
            query = f"""
            MATCH (n:Entity)
            {tenant_filter}
            OPTIONAL MATCH (n)-[r_out]->()
            OPTIONAL MATCH ()-[r_in]->(n)
            WITH n, count(DISTINCT r_out) AS out_degree, count(DISTINCT r_in) AS in_degree
            WITH n, out_degree, in_degree, 
                 (out_degree + in_degree + coalesce(n.complexity, 0)) AS risk_score
            WHERE risk_score > 0
            RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer,
                   coalesce(n.complexity, 0) AS complexity,
                   out_degree, in_degree, risk_score
            ORDER BY risk_score DESC
            LIMIT $limit
            """
            
            result = self.neo4j_service.graph.run(query, **params).data()
            return result
        except Exception as e:
            logger.error(f"Failed to get hotspots: {e}")
            return []
