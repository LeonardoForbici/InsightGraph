"""
Investigation Engine for AI-powered root cause analysis and guided investigation.

This module provides comprehensive investigation capabilities including:
- Root cause analysis using AI
- Impact chain building with BFS traversal
- Suggestion generation based on node characteristics
- Blast radius calculation
- Critical path identification
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Literal
import httpx

logger = logging.getLogger(__name__)


@dataclass
class RootCauseAnalysis:
    """Root cause analysis result."""
    primary_cause: str
    contributing_factors: List[str]
    confidence: float  # 0.0 to 1.0


@dataclass
class ImpactLevel:
    """Single level in the impact chain."""
    depth: int
    nodes: List[dict]
    relationships: List[str]


@dataclass
class ImpactChain:
    """Complete impact chain with multiple levels."""
    levels: List[ImpactLevel]
    total_affected: int
    max_depth: int


@dataclass
class Suggestion:
    """Actionable suggestion for improvement."""
    type: Literal['refactor', 'test', 'document', 'review']
    title: str
    description: str
    priority: Literal['high', 'medium', 'low']
    actionable: bool


@dataclass
class InvestigationData:
    """Complete investigation result."""
    target_node: dict
    root_cause: RootCauseAnalysis
    impact_chain: ImpactChain
    suggestions: List[Suggestion]
    blast_radius: int
    critical_path: List[str]


class InvestigationEngine:
    """
    Engine for comprehensive code investigation and analysis.
    
    Provides AI-powered root cause analysis, impact chain building,
    and actionable suggestions for code improvements.
    """
    
    def __init__(
        self,
        neo4j_service,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3.5:4b"
    ):
        """
        Initialize InvestigationEngine.
        
        Args:
            neo4j_service: Neo4j service instance for graph queries
            ollama_url: URL for Ollama API
            ollama_model: Model to use for AI analysis
        """
        self.neo4j = neo4j_service
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
    
    async def investigate(self, node_key: str) -> InvestigationData:
        """
        Perform comprehensive investigation of a node.
        
        Coordinates parallel analysis tasks including root cause analysis,
        impact chain building, and suggestion generation.
        
        Args:
            node_key: Namespace key of the node to investigate
        
        Returns:
            Complete investigation data
        
        Requirements:
            - 8.1: Main entry point for investigation
            - 8.2: Root cause analysis
            - 8.3: Impact chain building
            - 8.4: Suggestion generation
        """
        # Fetch target node
        target_node = await self._fetch_node(node_key)
        if not target_node:
            raise ValueError(f"Node not found: {node_key}")
        
        # Run parallel analysis
        import asyncio
        root_cause, impact_chain, suggestions = await asyncio.gather(
            self.analyze_root_cause(node_key, target_node),
            self.build_impact_chain(node_key),
            self.generate_suggestions(node_key, target_node)
        )
        
        # Calculate blast radius and critical path
        blast_radius = self.calculate_blast_radius(impact_chain)
        critical_path = self.find_critical_path(impact_chain)
        
        return InvestigationData(
            target_node=target_node,
            root_cause=root_cause,
            impact_chain=impact_chain,
            suggestions=suggestions,
            blast_radius=blast_radius,
            critical_path=critical_path
        )
    
    async def _fetch_node(self, node_key: str) -> Optional[dict]:
        """Fetch node data from Neo4j."""
        if not self.neo4j.is_connected:
            return None
        
        try:
            query = "MATCH (n:Entity {namespace_key: $key}) RETURN n"
            result = self.neo4j.graph.run(query, key=node_key).data()
            
            if result:
                node = result[0]["n"]
                node_data = dict(node)
                node_data["labels"] = list(node.labels)
                return node_data
            
            return None
        except Exception as e:
            logger.error(f"Failed to fetch node {node_key}: {e}")
            return None
    
    async def analyze_root_cause(
        self,
        node_key: str,
        node_data: dict
    ) -> RootCauseAnalysis:
        """
        Analyze root cause of why a node is problematic.
        
        Uses AI to analyze node context and identify primary causes
        and contributing factors.
        
        Args:
            node_key: Node namespace key
            node_data: Node data dictionary
        
        Returns:
            Root cause analysis with confidence score
        
        Requirements:
            - 8.2: AI-powered root cause analysis
        """
        try:
            # Build context for AI
            context = await self._build_node_context(node_key, node_data)
            
            # Query AI for root cause analysis
            prompt = f"""Analyze why this code element is problematic:

{context}

Identify:
1. Primary cause (main reason for the problem)
2. Contributing factors (secondary issues)

Be concise and specific."""
            
            response = await self._query_ollama(prompt)
            
            # Parse response (simplified - in production, use more robust parsing)
            lines = response.strip().split('\n')
            primary_cause = "High complexity and coupling"
            contributing_factors = ["Insufficient test coverage", "Frequent changes"]
            
            # Extract from response if possible
            for i, line in enumerate(lines):
                if 'primary' in line.lower() or '1.' in line:
                    primary_cause = lines[i + 1] if i + 1 < len(lines) else primary_cause
                elif 'contributing' in line.lower() or '2.' in line:
                    contributing_factors = [lines[j].strip('- ') for j in range(i + 1, min(i + 4, len(lines)))]
            
            # Calculate confidence based on available data
            confidence = 0.7
            if node_data.get('complexity', 0) > 10:
                confidence += 0.1
            if node_data.get('hotspot_score', 0) > 50:
                confidence += 0.1
            confidence = min(1.0, confidence)
            
            return RootCauseAnalysis(
                primary_cause=primary_cause,
                contributing_factors=contributing_factors,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"Root cause analysis failed: {e}")
            return RootCauseAnalysis(
                primary_cause="Analysis unavailable",
                contributing_factors=[],
                confidence=0.0
            )
    
    async def _build_node_context(self, node_key: str, node_data: dict) -> str:
        """Build text context about a node for AI analysis."""
        lines = [
            f"Node: {node_data.get('name', 'Unknown')}",
            f"Type: {node_data.get('labels', ['Unknown'])[0]}",
            f"Complexity: {node_data.get('complexity', 'N/A')}",
            f"Lines of Code: {node_data.get('loc', 'N/A')}",
            f"Hotspot Score: {node_data.get('hotspot_score', 'N/A')}",
            f"Layer: {node_data.get('layer', 'N/A')}",
        ]
        
        # Add dependency info
        if self.neo4j.is_connected:
            try:
                query = """
                MATCH (n:Entity {namespace_key: $key})
                OPTIONAL MATCH (n)-[r1]->(downstream)
                OPTIONAL MATCH (upstream)-[r2]->(n)
                RETURN count(DISTINCT downstream) AS downstream_count,
                       count(DISTINCT upstream) AS upstream_count
                """
                result = self.neo4j.graph.run(query, key=node_key).data()
                if result:
                    lines.append(f"Dependencies: {result[0]['downstream_count']} downstream, {result[0]['upstream_count']} upstream")
            except Exception:
                pass
        
        return '\n'.join(lines)
    
    async def _query_ollama(self, prompt: str) -> str:
        """Query Ollama API for AI analysis."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "")
                else:
                    logger.error(f"Ollama API error: {response.status_code}")
                    return ""
        except Exception as e:
            logger.error(f"Failed to query Ollama: {e}")
            return ""
    
    async def build_impact_chain(self, node_key: str) -> ImpactChain:
        """
        Build complete impact chain using BFS traversal.
        
        Organizes nodes by depth level and tracks relationships
        between levels.
        
        Args:
            node_key: Starting node key
        
        Returns:
            Impact chain with all levels
        
        Requirements:
            - 8.3: BFS-based impact chain building
        """
        levels: List[ImpactLevel] = []
        visited = set([node_key])
        current_level = [node_key]
        depth = 0
        max_depth = 10
        
        if not self.neo4j.is_connected:
            return ImpactChain(levels=[], total_affected=0, max_depth=0)
        
        try:
            while current_level and depth < max_depth:
                # Fetch nodes at current level
                nodes = []
                relationships = []
                next_level = []
                
                for current_key in current_level:
                    # Get downstream dependencies
                    query = """
                    MATCH (n:Entity {namespace_key: $key})-[r]->(downstream:Entity)
                    RETURN downstream, type(r) AS rel_type
                    LIMIT 50
                    """
                    result = self.neo4j.graph.run(query, key=current_key).data()
                    
                    for record in result:
                        downstream = record["downstream"]
                        downstream_key = downstream["namespace_key"]
                        
                        if downstream_key not in visited:
                            visited.add(downstream_key)
                            next_level.append(downstream_key)
                            
                            node_data = dict(downstream)
                            node_data["labels"] = list(downstream.labels)
                            nodes.append(node_data)
                            
                            relationships.append(record["rel_type"])
                
                if nodes:
                    levels.append(ImpactLevel(
                        depth=depth,
                        nodes=nodes,
                        relationships=list(set(relationships))
                    ))
                
                current_level = next_level
                depth += 1
            
            return ImpactChain(
                levels=levels,
                total_affected=len(visited) - 1,  # Exclude origin node
                max_depth=depth
            )
            
        except Exception as e:
            logger.error(f"Failed to build impact chain: {e}")
            return ImpactChain(levels=[], total_affected=0, max_depth=0)
    
    async def generate_suggestions(
        self,
        node_key: str,
        node_data: dict
    ) -> List[Suggestion]:
        """
        Generate actionable suggestions based on node characteristics.
        
        Args:
            node_key: Node namespace key
            node_data: Node data dictionary
        
        Returns:
            List of prioritized suggestions
        
        Requirements:
            - 8.4: Context-aware suggestion generation
        """
        suggestions = []
        
        complexity = node_data.get('complexity', 0)
        loc = node_data.get('loc', 0)
        hotspot_score = node_data.get('hotspot_score', 0)
        
        # High complexity suggestions
        if complexity > 15:
            suggestions.append(Suggestion(
                type='refactor',
                title='Reduce Complexity',
                description=f'This component has high cyclomatic complexity ({complexity}). Consider breaking it into smaller, focused functions.',
                priority='high',
                actionable=True
            ))
        
        # Large file suggestions
        if loc > 500:
            suggestions.append(Suggestion(
                type='refactor',
                title='Split Large File',
                description=f'This file has {loc} lines of code. Consider splitting it into multiple smaller files for better maintainability.',
                priority='medium',
                actionable=True
            ))
        
        # Hotspot suggestions
        if hotspot_score > 70:
            suggestions.append(Suggestion(
                type='test',
                title='Add Test Coverage',
                description='This is a hotspot (frequently changed). Ensure comprehensive test coverage to prevent regressions.',
                priority='high',
                actionable=True
            ))
        
        # Documentation suggestions for public APIs
        labels = node_data.get('labels', [])
        if any(label in ['Java_Class', 'TS_Component', 'TS_Function'] for label in labels):
            suggestions.append(Suggestion(
                type='document',
                title='Add Documentation',
                description='Public API components should have comprehensive documentation including usage examples.',
                priority='medium',
                actionable=True
            ))
        
        # Code review suggestion for high-risk changes
        if complexity > 10 and hotspot_score > 50:
            suggestions.append(Suggestion(
                type='review',
                title='Require Code Review',
                description='This component is complex and frequently changed. Require thorough code review for all changes.',
                priority='high',
                actionable=True
            ))
        
        return suggestions
    
    def calculate_blast_radius(self, impact_chain: ImpactChain) -> int:
        """
        Calculate blast radius with weighted distance.
        
        Closer nodes have higher weight in the calculation.
        
        Args:
            impact_chain: Impact chain data
        
        Returns:
            Blast radius score
        
        Requirements:
            - 8.5: Weighted blast radius calculation
        """
        radius = 0
        
        for level in impact_chain.levels:
            weight = 1.0 / (level.depth + 1)
            radius += len(level.nodes) * weight
        
        return round(radius)
    
    def find_critical_path(self, impact_chain: ImpactChain) -> List[str]:
        """
        Find critical path with highest cumulative complexity.
        
        Uses DFS to find the path through the impact chain with
        the highest total complexity.
        
        Args:
            impact_chain: Impact chain data
        
        Returns:
            List of node keys in critical path
        
        Requirements:
            - 8.6: Critical path identification
        """
        if not impact_chain.levels:
            return []
        
        max_path = []
        max_complexity = 0
        
        def dfs(path: List[str], complexity: int, depth: int):
            nonlocal max_path, max_complexity
            
            if depth >= len(impact_chain.levels):
                if complexity > max_complexity:
                    max_complexity = complexity
                    max_path = path.copy()
                return
            
            level = impact_chain.levels[depth]
            for node in level.nodes:
                node_key = node.get('namespace_key', '')
                node_complexity = node.get('complexity', 1)
                
                dfs(
                    path + [node_key],
                    complexity + node_complexity,
                    depth + 1
                )
        
        # Start DFS from first level
        if impact_chain.levels:
            for node in impact_chain.levels[0].nodes:
                dfs(
                    [node.get('namespace_key', '')],
                    node.get('complexity', 1),
                    1
                )
        
        return max_path
