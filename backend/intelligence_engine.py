"""
Intelligence Engine - Calculates critical risks, hotspots, and instabilities.

This module provides intelligence summaries for the sidebar intelligence panel,
identifying the most critical issues in the codebase.
"""

from typing import List, Dict, Any, Literal
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskItem:
    """Represents a critical risk in the codebase."""
    node_key: str
    name: str
    severity: Literal['critical', 'high', 'medium', 'low']
    score: float
    trend: Literal['improving', 'worsening', 'stable']
    reason: str


@dataclass
class HotspotItem:
    """Represents a hotspot (frequently changed area)."""
    node_key: str
    name: str
    hotspot_score: float
    complexity: int
    change_frequency: int


@dataclass
class InstabilityItem:
    """Represents an unstable node (frequent changes + high impact)."""
    node_key: str
    name: str
    change_count: int
    impact_radius: int
    last_changed: str


@dataclass
class IntelligenceSummary:
    """Complete intelligence summary for the sidebar."""
    risks: List[RiskItem]
    hotspots: List[HotspotItem]
    instabilities: List[InstabilityItem]


class IntelligenceEngine:
    """
    Calculates intelligence summaries from graph data.
    
    Provides:
    - Critical risks (top 10 by risk score)
    - Top hotspots (top 10 by hotspot_score)
    - Instabilities (high change_frequency + high impact)
    """
    
    def __init__(self, neo4j_service):
        """
        Initialize the intelligence engine.
        
        Args:
            neo4j_service: Neo4j service for querying graph data
        """
        self.neo4j = neo4j_service
    
    def calculate_summary(self) -> IntelligenceSummary:
        """
        Calculate complete intelligence summary.
        
        Returns:
            IntelligenceSummary with risks, hotspots, and instabilities
        """
        risks = self.calculate_critical_risks()
        hotspots = self.calculate_top_hotspots()
        instabilities = self.calculate_instabilities()
        
        return IntelligenceSummary(
            risks=risks,
            hotspots=hotspots,
            instabilities=instabilities
        )
    
    def calculate_critical_risks(self) -> List[RiskItem]:
        """
        Calculate top 10 critical risks by risk score.
        
        Risk score is calculated from:
        - Complexity
        - Hotspot score
        - Number of dependencies
        
        Returns:
            List of RiskItem objects, sorted by severity
        """
        query = """
        MATCH (n)
        WHERE n.complexity IS NOT NULL
        WITH n,
             COALESCE(n.complexity, 0) as complexity,
             COALESCE(n.hotspot_score, 0) as hotspot,
             size((n)-[:DEPENDS_ON]->()) as dependencies
        WITH n, complexity, hotspot, dependencies,
             (complexity * 0.4 + hotspot * 0.4 + dependencies * 0.2) as risk_score
        WHERE risk_score > 0
        RETURN n.namespace_key as node_key,
               n.name as name,
               risk_score,
               complexity,
               hotspot,
               dependencies
        ORDER BY risk_score DESC
        LIMIT 10
        """
        
        try:
            graph = getattr(self.neo4j, 'graph', self.neo4j)
            if hasattr(self.neo4j, 'is_connected') and not self.neo4j.is_connected:
                logger.warning('Neo4j is not connected; returning empty critical risks.')
                return []

            result = graph.run(query).data()
            risks = []
            for record in result:
                risk_score = record['risk_score']

                # Determine severity
                if risk_score >= 80:
                    severity = 'critical'
                elif risk_score >= 60:
                    severity = 'high'
                elif risk_score >= 40:
                    severity = 'medium'
                else:
                    severity = 'low'

                # Generate reason
                reasons = []
                if record['complexity'] > 20:
                    reasons.append(f"alta complexidade ({record['complexity']})")
                if record['hotspot'] > 70:
                    reasons.append(f"hotspot crítico ({record['hotspot']:.0f})")
                if record['dependencies'] > 10:
                    reasons.append(f"muitas dependências ({record['dependencies']})")

                reason = ", ".join(reasons) if reasons else "múltiplos fatores"

                # TODO: Calculate trend from historical data
                trend = 'stable'

                risks.append(RiskItem(
                    node_key=record['node_key'],
                    name=record['name'],
                    severity=severity,
                    score=risk_score,
                    trend=trend,
                    reason=reason
                ))

            return risks

        except Exception as e:
            logger.error(f"Failed to calculate critical risks: {e}")
            return []
    
    def calculate_top_hotspots(self) -> List[HotspotItem]:
        """
        Calculate top 10 hotspots by hotspot_score.
        
        Hotspots are areas that change frequently and have high complexity.
        
        Returns:
            List of HotspotItem objects, sorted by hotspot_score
        """
        query = """
        MATCH (n)
        WHERE n.hotspot_score IS NOT NULL AND n.hotspot_score > 0
        RETURN n.namespace_key as node_key,
               n.name as name,
               n.hotspot_score as hotspot_score,
               COALESCE(n.complexity, 0) as complexity,
               COALESCE(n.change_frequency, 0) as change_frequency
        ORDER BY n.hotspot_score DESC
        LIMIT 10
        """
        
        try:
            graph = getattr(self.neo4j, 'graph', self.neo4j)
            if hasattr(self.neo4j, 'is_connected') and not self.neo4j.is_connected:
                logger.warning('Neo4j is not connected; returning empty hotspots.')
                return []

            result = graph.run(query).data()
            hotspots = []
            for record in result:
                hotspots.append(HotspotItem(
                    node_key=record['node_key'],
                    name=record['name'],
                    hotspot_score=record['hotspot_score'],
                    complexity=record['complexity'],
                    change_frequency=record['change_frequency']
                ))

            return hotspots

        except Exception as e:
            logger.error(f"Failed to calculate top hotspots: {e}")
            return []
    
    def calculate_instabilities(self) -> List[InstabilityItem]:
        """
        Calculate instabilities (high change_frequency + high impact).
        
        Instabilities are nodes that:
        - Change frequently (change_frequency > 5)
        - Have high impact (many downstream dependencies)
        
        Returns:
            List of InstabilityItem objects, sorted by instability score
        """
        query = """
        MATCH (n)
        WHERE n.change_frequency IS NOT NULL AND n.change_frequency > 5
        WITH n,
             n.change_frequency as change_count,
             size((n)<-[:DEPENDS_ON*1..3]-()) as impact_radius
        WHERE impact_radius > 10
        RETURN n.namespace_key as node_key,
               n.name as name,
               change_count,
               impact_radius,
               COALESCE(n.last_modified, 'unknown') as last_changed
        ORDER BY (change_count * impact_radius) DESC
        LIMIT 10
        """
        
        try:
            graph = getattr(self.neo4j, 'graph', self.neo4j)
            if hasattr(self.neo4j, 'is_connected') and not self.neo4j.is_connected:
                logger.warning('Neo4j is not connected; returning empty instabilities.')
                return []

            result = graph.run(query).data()
            instabilities = []
            for record in result:
                instabilities.append(InstabilityItem(
                    node_key=record['node_key'],
                    name=record['name'],
                    change_count=record['change_count'],
                    impact_radius=record['impact_radius'],
                    last_changed=record['last_changed']
                ))

            return instabilities

        except Exception as e:
            logger.error(f"Failed to calculate instabilities: {e}")
            return []
    
    def to_dict(self, summary: IntelligenceSummary) -> Dict[str, Any]:
        """
        Convert IntelligenceSummary to dictionary for JSON serialization.
        
        Args:
            summary: IntelligenceSummary object
            
        Returns:
            Dictionary representation
        """
        return {
            'risks': [
                {
                    'node_key': r.node_key,
                    'name': r.name,
                    'severity': r.severity,
                    'score': r.score,
                    'trend': r.trend,
                    'reason': r.reason
                }
                for r in summary.risks
            ],
            'hotspots': [
                {
                    'node_key': h.node_key,
                    'name': h.name,
                    'hotspot_score': h.hotspot_score,
                    'complexity': h.complexity,
                    'change_frequency': h.change_frequency
                }
                for h in summary.hotspots
            ],
            'instabilities': [
                {
                    'node_key': i.node_key,
                    'name': i.name,
                    'change_count': i.change_count,
                    'impact_radius': i.impact_radius,
                    'last_changed': i.last_changed
                }
                for i in summary.instabilities
            ]
        }
