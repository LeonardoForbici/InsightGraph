"""
CrossProjectImpactEngine — Propagação de impacto entre projetos vinculados.

Quando um arquivo muda no Projeto A (backend), este motor:
  1. Extrai os símbolos alterados (classes, métodos, endpoints, tipos)
  2. Varre os projetos irmãos (frontend, mobile, shared...)
  3. Detecta quais deles CONSOMEM esses símbolos via:
     - Chamadas diretas (CALLS / CALLS_RESOLVED)
     - Contratos HTTP (CALLS_HTTP / CONSUMES_API)
     - Tipos compartilhados (HAS_FIELD / MAPS_TO_COLUMN)
     - Importações diretas (IMPORTS)
  4. Classifica o impacto: BREAKING | DEGRADED | INFORMATIONAL
  5. Publica CrossProjectImpactEvent via Redis pub/sub

Isso é o que transforma o InsightGraph em algo que nenhuma outra
ferramenta (nem o CAST) faz em tempo real no Ctrl+S.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

logger = logging.getLogger("insightgraph.cross_impact")

ImpactSeverity = Literal["BREAKING", "DEGRADED", "INFORMATIONAL"]

# Relações que cruzam fronteiras de projeto
CROSS_BOUNDARY_RELS = [
    "CALLS", "CALLS_RESOLVED", "CALLS_HTTP", "CONSUMES_API",
    "IMPORTS", "HAS_FIELD", "MAPS_TO_COLUMN", "DISPLAYED_BY",
    "CALLS_NHOP",
]


# ─────────────────────────────────────────────
# Modelos de dados
# ─────────────────────────────────────────────

@dataclass
class AffectedProjectNode:
    project_id: str
    project_name: str
    namespace_key: str
    symbol_name: str
    rel_type: str           # qual relação conecta os dois
    severity: ImpactSeverity
    call_chain: list[str]   # caminho do nó alterado até este nó
    confidence: int         # 0–100


@dataclass
class CrossProjectImpactResult:
    origin_project_id: str
    origin_file: str
    changed_symbols: list[str]
    affected_in_siblings: list[AffectedProjectNode]
    total_affected: int
    breaking_count: int
    timestamp: float = field(default_factory=time.time)

    def to_sse_payload(self) -> dict:
        return {
            "origin_project_id": self.origin_project_id,
            "origin_file": self.origin_file,
            "changed_symbols": self.changed_symbols,
            "total_affected": self.total_affected,
            "breaking_count": self.breaking_count,
            "affected": [asdict(n) for n in self.affected_in_siblings],
            "timestamp": self.timestamp,
        }


# ─────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────

class CrossProjectImpactEngine:
    """
    Analisa impacto de uma mudança em um projeto sobre todos os projetos
    irmãos do mesmo workspace.

    Não bloqueia: usa asyncio + leituras leves ao grafo em memória.
    A análise completa ao Neo4j só ocorre quando o grafo em memória
    não tem resolução suficiente.
    """

    def __init__(
        self,
        registry,           # ProjectRegistry
        memory_nodes: list[dict],
        memory_edges: list[dict],
        neo4j_service=None, # opcional — fallback para consulta profunda
        event_stream=None,  # EventStream para SSE
        redis_client=None,  # RedisClient para pub/sub entre workers
    ):
        self._registry = registry
        self._mem_nodes = memory_nodes
        self._mem_edges = memory_edges
        self._neo4j = neo4j_service
        self._stream = event_stream
        self._redis = redis_client

        # Índice invertido: symbol_key → list[node_dict]
        # Rebuilt quando memory_nodes muda (lazy, por projeto)
        self._symbol_index: dict[str, list[dict]] = {}
        self._index_dirty = True

    # ── Índice ────────────────────────────────

    def mark_index_dirty(self):
        self._index_dirty = True

    def _rebuild_index(self):
        idx: dict[str, list[dict]] = {}
        for n in self._mem_nodes:
            key = n.get("namespace_key") or n.get("id", "")
            if key:
                idx.setdefault(key, []).append(n)
            # Também indexa por nome simples para heurística
            name = n.get("name", "")
            if name and name != key:
                idx.setdefault(name, []).append(n)
        self._symbol_index = idx
        self._index_dirty = False
        logger.debug("Symbol index rebuilt: %d entries", len(idx))

    # ── API pública ───────────────────────────

    async def analyze(
        self,
        origin_project_id: str,
        changed_file: str,
        changed_nodes: list[str],  # namespace_keys dos nós alterados
    ) -> CrossProjectImpactResult:
        """
        Ponto de entrada principal.  Chamado pelo ProjectWorker após
        cada scan incremental bem-sucedido.

        Retorna CrossProjectImpactResult e publica eventos SSE/Redis.
        """
        t0 = time.monotonic()

        if self._index_dirty:
            self._rebuild_index()

        siblings = self._registry.get_sibling_projects(origin_project_id)
        if not siblings:
            return CrossProjectImpactResult(
                origin_project_id=origin_project_id,
                origin_file=changed_file,
                changed_symbols=changed_nodes,
                affected_in_siblings=[],
                total_affected=0,
                breaking_count=0,
            )

        sibling_ids = {s.id for s in siblings}
        sibling_map = {s.id: s for s in siblings}

        affected: list[AffectedProjectNode] = []

        for changed_key in changed_nodes:
            hits = await self._find_consumers(changed_key, sibling_ids, sibling_map)
            affected.extend(hits)

        # Deduplica por (project_id, namespace_key)
        seen: set[tuple] = set()
        deduped: list[AffectedProjectNode] = []
        for a in affected:
            k = (a.project_id, a.namespace_key)
            if k not in seen:
                seen.add(k)
                deduped.append(a)

        breaking = sum(1 for a in deduped if a.severity == "BREAKING")

        result = CrossProjectImpactResult(
            origin_project_id=origin_project_id,
            origin_file=changed_file,
            changed_symbols=changed_nodes,
            affected_in_siblings=deduped,
            total_affected=len(deduped),
            breaking_count=breaking,
        )

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "Cross-project analysis: %d affected nodes in %d siblings (%.1fms)",
            len(deduped), len(siblings), elapsed,
        )

        await self._publish(result)
        return result

    # ── Busca de consumidores ─────────────────

    async def _find_consumers(
        self,
        changed_key: str,
        sibling_ids: set[str],
        sibling_map: dict,
    ) -> list[AffectedProjectNode]:
        """
        Busca nós nos projetos irmãos que dependem de changed_key.

        Estratégia em camadas (do mais rápido ao mais lento):
          L1 — Arestas diretas no grafo em memória
          L2 — Busca por nome heurística no índice
          L3 — Consulta ao Neo4j (apenas se L1+L2 retornarem 0 resultados)
        """
        results: list[AffectedProjectNode] = []

        # L1: arestas diretas
        for edge in self._mem_edges:
            if edge.get("source") != changed_key:
                continue
            rel = edge.get("type", "")
            if rel not in CROSS_BOUNDARY_RELS:
                continue
            target_key = edge.get("target", "")
            target_nodes = self._symbol_index.get(target_key, [])
            for tn in target_nodes:
                proj_id = tn.get("project_id", "")
                if proj_id not in sibling_ids:
                    continue
                sib = sibling_map[proj_id]
                sev = self._classify_severity(rel, tn)
                results.append(AffectedProjectNode(
                    project_id=proj_id,
                    project_name=sib.name,
                    namespace_key=target_key,
                    symbol_name=tn.get("name", target_key),
                    rel_type=rel,
                    severity=sev,
                    call_chain=[changed_key, target_key],
                    confidence=90,
                ))

        # L2: heurística por nome (APIs REST, tipos exportados)
        if not results:
            symbol_name = changed_key.split(".")[-1]  # pega só o nome curto
            candidates = self._symbol_index.get(symbol_name, [])
            for cn in candidates:
                proj_id = cn.get("project_id", "")
                if proj_id not in sibling_ids:
                    continue
                sib = sibling_map[proj_id]
                results.append(AffectedProjectNode(
                    project_id=proj_id,
                    project_name=sib.name,
                    namespace_key=cn.get("namespace_key", symbol_name),
                    symbol_name=symbol_name,
                    rel_type="HEURISTIC_NAME_MATCH",
                    severity="INFORMATIONAL",
                    call_chain=[changed_key, cn.get("namespace_key", symbol_name)],
                    confidence=55,
                ))

        # L3: Neo4j (assíncrono, só se necessário)
        if not results and self._neo4j:
            results = await self._neo4j_query(changed_key, sibling_ids, sibling_map)

        return results

    async def _neo4j_query(
        self,
        changed_key: str,
        sibling_ids: set[str],
        sibling_map: dict,
    ) -> list[AffectedProjectNode]:
        """Consulta profunda ao Neo4j para impacto cross-projeto."""
        try:
            loop = asyncio.get_event_loop()
            query = """
                MATCH (origin {namespace_key: $key})
                MATCH (origin)-[r]-(target)
                WHERE type(r) IN $rels AND target.project_id IN $projects
                RETURN target.namespace_key AS ns_key,
                       target.name AS name,
                       target.project_id AS proj_id,
                       type(r) AS rel_type
                LIMIT 50
            """
            rows = await loop.run_in_executor(
                None,
                lambda: self._neo4j.run_query(
                    query,
                    key=changed_key,
                    rels=CROSS_BOUNDARY_RELS,
                    projects=list(sibling_ids),
                ),
            )
            out = []
            for row in (rows or []):
                proj_id = row.get("proj_id", "")
                if proj_id not in sibling_ids:
                    continue
                sib = sibling_map[proj_id]
                rel = row.get("rel_type", "CALLS")
                tn = {"project_id": proj_id}
                sev = self._classify_severity(rel, tn)
                out.append(AffectedProjectNode(
                    project_id=proj_id,
                    project_name=sib.name,
                    namespace_key=row.get("ns_key", ""),
                    symbol_name=row.get("name", ""),
                    rel_type=rel,
                    severity=sev,
                    call_chain=[changed_key, row.get("ns_key", "")],
                    confidence=80,
                ))
            return out
        except Exception as exc:
            logger.warning("Neo4j cross-project query failed: %s", exc)
            return []

    # ── Classificação de severidade ───────────

    @staticmethod
    def _classify_severity(rel_type: str, target_node: dict) -> ImpactSeverity:
        """
        BREAKING  → contrato público alterado (API, tipo exportado)
        DEGRADED  → chamada interna impactada
        INFORMATIONAL → heurística ou baixa confiança
        """
        breaking_rels = {"CALLS_HTTP", "CONSUMES_API", "MAPS_TO_COLUMN", "DISPLAYED_BY"}
        degraded_rels  = {"CALLS", "CALLS_RESOLVED", "CALLS_NHOP", "IMPORTS"}

        if rel_type in breaking_rels:
            return "BREAKING"
        if rel_type in degraded_rels:
            return "DEGRADED"
        return "INFORMATIONAL"

    # ── Publicação ────────────────────────────

    async def _publish(self, result: CrossProjectImpactResult):
        if result.total_affected == 0:
            return

        payload = result.to_sse_payload()

        # SSE direto para clientes conectados
        if self._stream:
            try:
                from event_stream import SSEEvent
                await self._stream.publish(SSEEvent(
                    type="impact_detected",
                    payload={"cross_project": True, **payload},
                    timestamp=time.time(),
                ))
            except Exception as exc:
                logger.warning("SSE publish failed: %s", exc)

        # Redis pub/sub para outros workers/instâncias
        if self._redis:
            try:
                channel = f"workspace:cross_impact:{result.origin_project_id}"
                await self._redis.publish(channel, json.dumps(payload))
            except Exception as exc:
                logger.warning("Redis publish failed: %s", exc)
