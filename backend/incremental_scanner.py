"""
IncrementalScanner — Atualização parcial do grafo para arquivos modificados.

Integra com:
- Tree-Sitter parsers existentes (Java, TypeScript, SQL)
- Neo4j via neo4j_service.merge_node() e merge_relationship()
- RAG Store para embeddings
- ImpactEngine para cálculo de impacto
- Memory graph (memory_nodes, memory_edges)

Requirements: Task 4 (Watch Mode)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("insightgraph.incremental")


@dataclass
class ImpactResult:
    """Resultado do scan incremental de um arquivo."""
    file_path: str
    changed_nodes: list[str]        # namespace_keys dos nós alterados
    affected_nodes: list[str]       # nós impactados (dependentes)
    risk_score: float               # 0.0 a 100.0
    coupling_delta: float           # variação de acoplamento (+/-)
    summary: str                    # ex: "3 serviços impactados, risco +18%"
    timestamp: datetime


class IncrementalScanner:
    """
    Processa um único arquivo modificado e atualiza o grafo de forma incremental.
    
    Fluxo:
    1. Lê o arquivo modificado
    2. Identifica o tipo (Java / TypeScript / SQL)
    3. Faz reparse com Tree-Sitter
    4. Extrai classes, métodos, dependências, métricas
    5. MERGE nos nós existentes (atualiza propriedades)
    6. Remove arestas antigas do arquivo
    7. Cria novas arestas
    8. Atualiza memory_nodes e memory_edges
    9. Atualiza embeddings RAG
    10. Dispara ImpactEngine
    """

    def __init__(
        self,
        neo4j_service,
        rag_store,
        memory_nodes: list[dict],
        memory_edges: list[dict],
        parsers: dict,  # {"java": parser, "ts": parser, "tsx": parser}
        parse_functions: dict,  # {"java": parse_java, "ts": parse_typescript, ...}
    ):
        self._neo4j = neo4j_service
        self._rag = rag_store
        self._memory_nodes = memory_nodes
        self._memory_edges = memory_edges
        self._parsers = parsers
        self._parse_functions = parse_functions
        self._lock = asyncio.Lock()

    async def process_file(self, file_path: str, project_path: str = None) -> ImpactResult:
        """
        Processa um arquivo modificado e retorna o impacto.
        
        Args:
            file_path: Caminho absoluto do arquivo modificado
            project_path: Caminho raiz do projeto (para namespace)
            
        Returns:
            ImpactResult com os nós afetados e score de risco
        """
        start_time = time.monotonic()
        
        async with self._lock:
            try:
                # 1. Verificar se arquivo existe
                path = Path(file_path)
                if not path.exists():
                    logger.warning("Arquivo não existe (deletado?): %s", file_path)
                    return await self._handle_deleted_file(file_path)
                
                # 2. Ler conteúdo
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    logger.error("Erro ao ler arquivo %s: %s", file_path, e)
                    return ImpactResult(
                        file_path=file_path,
                        changed_nodes=[],
                        affected_nodes=[],
                        risk_score=0.0,
                        coupling_delta=0.0,
                        summary=f"Erro ao ler arquivo: {e}",
                        timestamp=datetime.now(),
                    )
                
                # 3. Identificar tipo e parser
                file_type = self._identify_file_type(file_path)
                if not file_type:
                    logger.debug("Tipo de arquivo não suportado: %s", file_path)
                    return ImpactResult(
                        file_path=file_path,
                        changed_nodes=[],
                        affected_nodes=[],
                        risk_score=0.0,
                        coupling_delta=0.0,
                        summary="Tipo de arquivo não suportado",
                        timestamp=datetime.now(),
                    )
                
                # 4. Parse com Tree-Sitter
                parse_fn = self._parse_functions.get(file_type)
                if not parse_fn:
                    logger.warning("Parser não encontrado para tipo: %s", file_type)
                    return ImpactResult(
                        file_path=file_path,
                        changed_nodes=[],
                        affected_nodes=[],
                        risk_score=0.0,
                        coupling_delta=0.0,
                        summary="Parser não disponível",
                        timestamp=datetime.now(),
                    )
                
                # Parse do arquivo
                project_root = project_path or str(path.parent)
                parsed_data = parse_fn(file_path, content, project_root)
                
                # 5. Extrair nós e arestas do resultado do parse
                new_nodes = parsed_data.get("nodes", [])
                new_edges = parsed_data.get("edges", [])
                
                if not new_nodes:
                    logger.debug("Nenhum nó extraído de %s", file_path)
                    return ImpactResult(
                        file_path=file_path,
                        changed_nodes=[],
                        affected_nodes=[],
                        risk_score=0.0,
                        coupling_delta=0.0,
                        summary="Nenhum nó encontrado no arquivo",
                        timestamp=datetime.now(),
                    )
                
                # 6. Calcular acoplamento ANTES da atualização
                old_coupling = self._calculate_file_coupling(file_path)
                
                # 7. Atualizar grafo (Neo4j + memória)
                changed_keys = await self._update_graph(file_path, new_nodes, new_edges)
                
                # 8. Calcular acoplamento DEPOIS da atualização
                new_coupling = self._calculate_file_coupling(file_path)
                coupling_delta = new_coupling - old_coupling
                
                # 9. Atualizar RAG embeddings
                await self._update_rag_embeddings(changed_keys)
                
                # 10. Calcular impacto (dependentes afetados)
                affected_keys, risk_score = await self._calculate_impact(changed_keys)
                
                # 11. Gerar summary
                summary = self._generate_summary(
                    len(changed_keys),
                    len(affected_keys),
                    risk_score,
                    coupling_delta,
                )
                
                elapsed = time.monotonic() - start_time
                logger.info(
                    "Scan incremental completo: %s (%d nós, %d afetados, risco %.1f, %.2fs)",
                    file_path,
                    len(changed_keys),
                    len(affected_keys),
                    risk_score,
                    elapsed,
                )
                
                return ImpactResult(
                    file_path=file_path,
                    changed_nodes=changed_keys,
                    affected_nodes=affected_keys,
                    risk_score=risk_score,
                    coupling_delta=coupling_delta,
                    summary=summary,
                    timestamp=datetime.now(),
                )
                
            except Exception as e:
                logger.error("Erro no scan incremental de %s: %s", file_path, e, exc_info=True)
                return ImpactResult(
                    file_path=file_path,
                    changed_nodes=[],
                    affected_nodes=[],
                    risk_score=0.0,
                    coupling_delta=0.0,
                    summary=f"Erro: {str(e)}",
                    timestamp=datetime.now(),
                )

    async def _handle_deleted_file(self, file_path: str) -> ImpactResult:
        """Remove nós de um arquivo deletado."""
        # Encontrar nós do arquivo
        deleted_keys = [
            n["namespace_key"]
            for n in self._memory_nodes
            if n.get("file") == file_path
        ]
        
        if not deleted_keys:
            return ImpactResult(
                file_path=file_path,
                changed_nodes=[],
                affected_nodes=[],
                risk_score=0.0,
                coupling_delta=0.0,
                summary="Arquivo não estava no grafo",
                timestamp=datetime.now(),
            )
        
        # Remover do Neo4j
        if self._neo4j.is_connected:
            try:
                for key in deleted_keys:
                    query = "MATCH (n:Entity {namespace_key: $key}) DETACH DELETE n"
                    self._neo4j.graph.run(query, key=key)
            except Exception as e:
                logger.error("Erro ao remover nós do Neo4j: %s", e)
        
        # Remover da memória
        self._memory_nodes[:] = [
            n for n in self._memory_nodes
            if n.get("file") != file_path
        ]
        self._memory_edges[:] = [
            e for e in self._memory_edges
            if e.get("source") not in deleted_keys and e.get("target") not in deleted_keys
        ]
        
        # Remover do RAG
        try:
            for key in deleted_keys:
                self._rag.delete_entry(key)
        except Exception as e:
            logger.warning("Erro ao remover embeddings RAG: %s", e)
        
        logger.info("Arquivo deletado: %s (%d nós removidos)", file_path, len(deleted_keys))
        
        return ImpactResult(
            file_path=file_path,
            changed_nodes=deleted_keys,
            affected_nodes=[],
            risk_score=0.0,
            coupling_delta=0.0,
            summary=f"{len(deleted_keys)} nós removidos",
            timestamp=datetime.now(),
        )

    def _identify_file_type(self, file_path: str) -> Optional[str]:
        """Identifica o tipo do arquivo pela extensão."""
        suffix = Path(file_path).suffix.lower()
        if suffix == ".java":
            return "java"
        if suffix in (".ts", ".tsx"):
            return "ts"
        if suffix in (".sql", ".prc", ".fnc", ".pkg"):
            return "sql"
        return None

    async def _update_graph(
        self,
        file_path: str,
        new_nodes: list[dict],
        new_edges: list[dict],
    ) -> list[str]:
        """
        Atualiza o grafo (Neo4j + memória) com os novos nós e arestas.
        
        Returns:
            Lista de namespace_keys dos nós alterados
        """
        changed_keys = []
        
        # 1. Remover arestas antigas do arquivo
        old_node_keys = {
            n["namespace_key"]
            for n in self._memory_nodes
            if n.get("file") == file_path
        }
        
        # Remover arestas antigas da memória
        self._memory_edges[:] = [
            e for e in self._memory_edges
            if e.get("source") not in old_node_keys and e.get("target") not in old_node_keys
        ]
        
        # Remover arestas antigas do Neo4j
        if self._neo4j.is_connected and old_node_keys:
            try:
                for key in old_node_keys:
                    query = "MATCH (n:Entity {namespace_key: $key})-[r]-() DELETE r"
                    self._neo4j.graph.run(query, key=key)
            except Exception as e:
                logger.warning("Erro ao remover arestas antigas do Neo4j: %s", e)
        
        # 2. MERGE nós (atualiza ou cria)
        for node in new_nodes:
            ns_key = node.get("namespace_key")
            if not ns_key:
                continue
            
            changed_keys.append(ns_key)
            
            # Atualizar Neo4j
            if self._neo4j.is_connected:
                try:
                    labels = node.get("labels", [])
                    label = labels[0] if labels else "Entity"
                    self._neo4j.merge_node(label, ns_key, node)
                except Exception as e:
                    logger.warning("Erro ao fazer MERGE no Neo4j para %s: %s", ns_key, e)
            
            # Atualizar memória
            existing_idx = next(
                (i for i, n in enumerate(self._memory_nodes) if n.get("namespace_key") == ns_key),
                None,
            )
            if existing_idx is not None:
                self._memory_nodes[existing_idx] = node
            else:
                self._memory_nodes.append(node)
        
        # 3. Criar novas arestas
        for edge in new_edges:
            src = edge.get("source")
            tgt = edge.get("target")
            rel_type = edge.get("type", "UNKNOWN")
            
            if not src or not tgt:
                continue
            
            # Adicionar ao Neo4j
            if self._neo4j.is_connected:
                try:
                    self._neo4j.merge_relationship(src, tgt, rel_type)
                except Exception as e:
                    logger.warning("Erro ao criar aresta %s -> %s: %s", src, tgt, e)
            
            # Adicionar à memória
            self._memory_edges.append(edge)
        
        return changed_keys

    def _calculate_file_coupling(self, file_path: str) -> float:
        """Calcula o acoplamento total dos nós de um arquivo."""
        file_nodes = {
            n["namespace_key"]
            for n in self._memory_nodes
            if n.get("file") == file_path
        }
        
        if not file_nodes:
            return 0.0
        
        # Contar arestas de entrada e saída
        in_degree = 0
        out_degree = 0
        
        for edge in self._memory_edges:
            src = edge.get("source")
            tgt = edge.get("target")
            
            if src in file_nodes:
                out_degree += 1
            if tgt in file_nodes:
                in_degree += 1
        
        return float(in_degree + out_degree)

    async def _update_rag_embeddings(self, node_keys: list[str]) -> None:
        """Atualiza embeddings RAG para os nós modificados."""
        if not node_keys:
            return
        
        try:
            for key in node_keys:
                node = next(
                    (n for n in self._memory_nodes if n.get("namespace_key") == key),
                    None,
                )
                if not node:
                    continue
                
                # Criar texto para embedding
                text = f"{node.get('name', '')} {node.get('file', '')} {node.get('layer', '')}"
                
                # Atualizar no RAG store (assume que tem método upsert_entry)
                try:
                    if hasattr(self._rag, "upsert_entry"):
                        self._rag.upsert_entry(key, text, node)
                except Exception as e:
                    logger.debug("Erro ao atualizar RAG para %s: %s", key, e)
        
        except Exception as e:
            logger.warning("Erro ao atualizar embeddings RAG: %s", e)

    async def _calculate_impact(self, changed_keys: list[str]) -> tuple[list[str], float]:
        """
        Calcula os nós afetados (dependentes) e o score de risco.
        
        Returns:
            (affected_keys, risk_score)
        """
        if not changed_keys:
            return [], 0.0
        
        affected = set()
        
        # BFS simples para encontrar dependentes diretos
        for key in changed_keys:
            for edge in self._memory_edges:
                if edge.get("source") == key:
                    tgt = edge.get("target")
                    if tgt and tgt not in changed_keys:
                        affected.add(tgt)
        
        affected_list = list(affected)
        
        # Calcular risk score baseado em:
        # - Número de nós afetados
        # - Complexidade dos nós afetados
        # - Acoplamento
        risk_score = min(100.0, len(affected_list) * 5.0)
        
        # Ajustar por complexidade
        for key in affected_list:
            node = next(
                (n for n in self._memory_nodes if n.get("namespace_key") == key),
                None,
            )
            if node:
                complexity = node.get("complexity", 1)
                risk_score += min(10.0, complexity * 0.5)
        
        risk_score = min(100.0, risk_score)
        
        return affected_list, risk_score

    def _generate_summary(
        self,
        changed_count: int,
        affected_count: int,
        risk_score: float,
        coupling_delta: float,
    ) -> str:
        """Gera um resumo textual do impacto."""
        parts = []
        
        if affected_count == 0:
            parts.append("Nenhum nó impactado")
        elif affected_count == 1:
            parts.append("1 nó impactado")
        else:
            parts.append(f"{affected_count} nós impactados")
        
        if coupling_delta > 0:
            parts.append(f"acoplamento +{coupling_delta:.0f}")
        elif coupling_delta < 0:
            parts.append(f"acoplamento {coupling_delta:.0f}")
        
        if risk_score > 70:
            parts.append(f"risco ALTO ({risk_score:.0f}%)")
        elif risk_score > 30:
            parts.append(f"risco médio ({risk_score:.0f}%)")
        else:
            parts.append(f"risco baixo ({risk_score:.0f}%)")
        
        return " — ".join(parts)
