"""
InvestigativeAI — decomposes a question into hypotheses, collects evidence from
the in-memory graph and snapshot history, and verifies each hypothesis.

Endpoint: POST /api/ask/investigate
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("insightgraph.investigative_ai")

MAX_HYPOTHESES = 5
CONFIDENCE_THRESHOLD = 0.4


# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

@dataclass
class Hypothesis:
    text: str
    keywords: list[str]


@dataclass
class Evidence:
    namespace_key: str
    description: str
    metric_value: float | None = None


@dataclass
class HypothesisResult:
    hypothesis: str
    verified: bool
    confidence: float
    evidence: list[str]  # namespace_keys


@dataclass
class InvestigationResult:
    answer: str
    hypotheses: list[HypothesisResult]
    evidence_nodes: list[str]  # namespace_keys for GraphCanvas highlight
    confidence: float
    model: str


# ──────────────────────────────────────────────
# InvestigativeAI
# ──────────────────────────────────────────────

class InvestigativeAI:
    """Investigates an architectural question by decomposing it into hypotheses,
    collecting evidence from the graph and snapshot history, and verifying each
    hypothesis with a confidence score."""

    def __init__(
        self,
        ollama_url: str,
        chat_model: str,
        state_store,
        neo4j_service,
        memory_nodes: list,
        memory_edges: list,
    ):
        self._ollama_url = ollama_url
        self._chat_model = chat_model
        self._state_store = state_store
        self._neo4j_service = neo4j_service
        self._nodes = memory_nodes
        self._edges = memory_edges

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def investigate(self, question: str) -> InvestigationResult:
        """Run the full investigation pipeline and return an InvestigationResult."""
        hypotheses = await self._decompose_to_hypotheses(question)

        results: list[HypothesisResult] = []
        all_evidence_keys: list[str] = []

        for hyp in hypotheses:
            evidence = await self._collect_evidence(hyp)
            result = await self._verify_hypothesis(hyp, evidence)
            results.append(result)
            all_evidence_keys.extend(result.evidence)

        # Deduplicate while preserving order
        seen: set[str] = set()
        evidence_nodes: list[str] = []
        for key in all_evidence_keys:
            if key not in seen:
                seen.add(key)
                evidence_nodes.append(key)

        overall_confidence = (
            sum(r.confidence for r in results) / len(results) if results else 0.0
        )

        answer = self._build_answer(question, results)

        return InvestigationResult(
            answer=answer,
            hypotheses=results,
            evidence_nodes=evidence_nodes,
            confidence=round(overall_confidence, 4),
            model=self._chat_model,
        )

    # ──────────────────────────────────────────────
    # Task 7.2 — Decompose question into hypotheses
    # ──────────────────────────────────────────────

    async def _decompose_to_hypotheses(self, question: str) -> list[Hypothesis]:
        """Call Ollama to decompose *question* into at most 5 verifiable hypotheses."""
        system_prompt = (
            "Você é um assistente de análise arquitetural. "
            "Dado uma pergunta sobre um sistema de software, decomponha-a em hipóteses verificáveis. "
            f"Retorne no máximo {MAX_HYPOTHESES} hipóteses como JSON com o formato:\n"
            '{"hypotheses": [{"text": "...", "keywords": ["kw1", "kw2"]}]}\n'
            "Cada hipótese deve ser concisa e verificável com dados do grafo de dependências."
        )
        prompt = f"Pergunta: {question}\n\nDecomponha em hipóteses verificáveis:"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/chat",
                    json={
                        "model": self._chat_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                hypotheses = self._parse_hypotheses(content)
                if hypotheses:
                    return hypotheses[:MAX_HYPOTHESES]
        except Exception as exc:
            logger.warning("Ollama decompose failed: %s — falling back to single hypothesis", exc)

        # Fallback: single hypothesis with the original question
        keywords = [w.lower() for w in re.split(r"\W+", question) if len(w) > 3][:5]
        return [Hypothesis(text=question, keywords=keywords)]

    # ──────────────────────────────────────────────
    # Task 7.3 — Collect evidence
    # ──────────────────────────────────────────────

    async def _collect_evidence(self, hypothesis: Hypothesis) -> list[Evidence]:
        """Search in-memory graph nodes and snapshot history for evidence."""
        evidence: list[Evidence] = []
        keywords_lower = [kw.lower() for kw in hypothesis.keywords]

        # Search in-memory graph nodes by keyword matching
        for node in self._nodes:
            node_key = node.get("namespace_key") or node.get("key") or node.get("id", "")
            if not node_key:
                continue
            searchable = " ".join(
                str(v) for v in node.values() if isinstance(v, str)
            ).lower()
            if any(kw in searchable for kw in keywords_lower):
                description = (
                    node.get("name")
                    or node.get("label")
                    or node.get("type", "")
                    or node_key
                )
                evidence.append(
                    Evidence(
                        namespace_key=node_key,
                        description=str(description),
                        metric_value=node.get("complexity") or node.get("score"),
                    )
                )

        # Search snapshot history for relevant metrics
        try:
            history = self._state_store.get_snapshots(page=1, limit=10)
            for snapshot in history:
                snap_text = json.dumps(snapshot).lower()
                if any(kw in snap_text for kw in keywords_lower):
                    snap_key = f"snapshot:{snapshot.get('id', '')}"
                    evidence.append(
                        Evidence(
                            namespace_key=snap_key,
                            description=f"Snapshot {snapshot.get('id', '')} — nodes={snapshot.get('total_nodes', 0)}",
                            metric_value=float(snapshot.get("call_resolution_rate") or 0.0),
                        )
                    )
        except Exception as exc:
            logger.debug("Snapshot history search failed: %s", exc)

        return evidence

    # ──────────────────────────────────────────────
    # Task 7.4 — Verify hypothesis
    # ──────────────────────────────────────────────

    async def _verify_hypothesis(
        self, hypothesis: Hypothesis, evidence: list[Evidence]
    ) -> HypothesisResult:
        """Calculate confidence based on evidence count and set verified flag."""
        evidence_count = len(evidence)

        # Confidence formula: saturates at 1.0 after 10 evidence items
        confidence = min(1.0, evidence_count / 10.0)
        verified = confidence >= CONFIDENCE_THRESHOLD

        # Collect namespace_keys from graph nodes only (exclude snapshot: keys for highlight)
        evidence_keys = [
            e.namespace_key
            for e in evidence
            if not e.namespace_key.startswith("snapshot:")
        ]

        return HypothesisResult(
            hypothesis=hypothesis.text,
            verified=verified,
            confidence=round(confidence, 4),
            evidence=evidence_keys,
        )

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _parse_hypotheses(self, content: str) -> list[Hypothesis]:
        """Parse Ollama JSON response into a list of Hypothesis objects."""
        # Try to extract JSON block from the response
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return []
        try:
            data = json.loads(json_match.group())
            raw_list = data.get("hypotheses", [])
            result = []
            for item in raw_list:
                if isinstance(item, dict) and "text" in item:
                    keywords = item.get("keywords", [])
                    if not isinstance(keywords, list):
                        keywords = []
                    result.append(Hypothesis(text=str(item["text"]), keywords=keywords))
            return result
        except (json.JSONDecodeError, TypeError) as exc:
            logger.debug("Failed to parse hypotheses JSON: %s", exc)
            return []

    def _build_answer(self, question: str, results: list[HypothesisResult]) -> str:
        """Build a human-readable answer summary from hypothesis results."""
        verified = [r for r in results if r.verified]
        unverified = [r for r in results if not r.verified]

        lines = [f"Investigação para: {question}\n"]
        if verified:
            lines.append(f"✅ {len(verified)} hipótese(s) verificada(s):")
            for r in verified:
                lines.append(f"  • {r.hypothesis} (confiança: {r.confidence:.0%})")
        if unverified:
            lines.append(f"❌ {len(unverified)} hipótese(s) não verificada(s):")
            for r in unverified:
                lines.append(f"  • {r.hypothesis} (confiança: {r.confidence:.0%})")
        if not results:
            lines.append("Nenhuma hipótese gerada.")

        return "\n".join(lines)
