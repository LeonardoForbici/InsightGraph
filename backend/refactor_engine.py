"""
RefactorEngine — Generates refactoring suggestions and architecture guidance
using the OLLAMA_COMPLEX_MODEL tier.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx

logger = logging.getLogger("insightgraph.refactor")


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

@dataclass
class RefactorSuggestion:
    node_key: str
    original_code: str
    suggested_code: str
    test_code: str
    problems: list
    dependents_to_update: list
    effort_estimate: str
    requires_review: bool = False


@dataclass
class ArchitectureSuggestion:
    description: str
    suggestion: str
    example_keys: list
    patterns: dict


# ──────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────

class RefactorEngine:
    def __init__(
        self,
        ollama_url: str,
        complex_model: str,
        state_store,
        memory_nodes: list,
        memory_edges: list,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.complex_model = complex_model
        self.state_store = state_store
        self.memory_nodes = memory_nodes
        self.memory_edges = memory_edges

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    async def suggest_refactor(self, node_key: str) -> RefactorSuggestion:
        """Generate a refactoring suggestion for the given node."""
        node = next(
            (n for n in self.memory_nodes if n.get("namespace_key") == node_key), None
        )
        if node is None:
            raise ValueError(f"Node '{node_key}' not found in memory graph")

        problems = self._identify_problems(node)
        dependents = self._find_dependents(node_key)

        original_code = node.get("code") or node.get("source") or f"# {node.get('name', node_key)}"

        # Build context for Ollama
        context = self._build_node_context(node, problems, dependents)

        requires_review = False
        suggested_code = ""
        test_code = ""

        try:
            suggested_code = await self._call_ollama_refactor(context, original_code)
        except Exception as exc:
            logger.warning("Ollama refactor call failed: %s", exc)
            suggested_code = f"# TODO: Refactor {node.get('name', node_key)}\n# Problems: {', '.join(problems)}"
            requires_review = True

        try:
            test_code = await self._call_ollama_tests(node, suggested_code)
        except Exception as exc:
            logger.warning("Ollama test generation failed: %s", exc)
            test_code = f"# TODO: Write unit tests for {node.get('name', node_key)}"
            requires_review = True

        effort = self._estimate_effort(problems, len(dependents))

        suggestion = RefactorSuggestion(
            node_key=node_key,
            original_code=original_code,
            suggested_code=suggested_code,
            test_code=test_code,
            problems=problems,
            dependents_to_update=dependents,
            effort_estimate=effort,
            requires_review=requires_review,
        )

        # Persist
        record = asdict(suggestion)
        record["id"] = str(uuid.uuid4())
        record["created_at"] = time.time()
        record["problems_json"] = json.dumps(problems)
        record["dependents_json"] = json.dumps(dependents)
        self.state_store.save_refactor_suggestion(record)

        return suggestion

    async def suggest_architecture(self, description: str) -> ArchitectureSuggestion:
        """Analyze graph patterns and suggest architecture for a new feature."""
        patterns = self._analyze_patterns()
        example_keys = [n["namespace_key"] for n in patterns.get("example_nodes", [])]

        context = self._build_architecture_context(description, patterns)

        suggestion_text = ""
        try:
            suggestion_text = await self._call_ollama_architecture(context)
        except Exception as exc:
            logger.warning("Ollama architecture call failed: %s", exc)
            suggestion_text = (
                f"# Sugestão de Arquitetura para: {description}\n\n"
                "Baseado nos padrões do grafo, considere seguir a estrutura existente de camadas."
            )

        return ArchitectureSuggestion(
            description=description,
            suggestion=suggestion_text,
            example_keys=example_keys,
            patterns=patterns,
        )

    def get_history(self) -> list:
        return self.state_store.get_refactor_suggestions()

    # ──────────────────────────────────────────
    # Problem Identification (Task 8.2)
    # ──────────────────────────────────────────

    def _identify_problems(self, node: dict) -> list:
        problems = []

        wmc = node.get("wmc", 0) or 0
        out_degree = node.get("out_degree", 0) or 0
        in_degree = node.get("in_degree", 0) or 0
        complexity = node.get("complexity", 0) or 0
        cbo = node.get("cbo", 0) or 0

        # God class
        if wmc > 20 or (out_degree + in_degree) > 15:
            problems.append(
                f"God class detectada: WMC={wmc}, grau total={out_degree + in_degree} "
                "(considere dividir em classes menores)"
            )

        # Alta complexidade
        if complexity > 15:
            problems.append(
                f"Alta complexidade ciclomática: {complexity} "
                "(considere extrair métodos)"
            )

        # Alto acoplamento
        if cbo > 10:
            problems.append(
                f"Alto acoplamento (CBO={cbo}): depende de muitas outras classes "
                "(considere inversão de dependência)"
            )

        return problems

    # ──────────────────────────────────────────
    # Dependents Finder
    # ──────────────────────────────────────────

    def _find_dependents(self, node_key: str) -> list:
        """Return namespace_keys of nodes that depend on (call/import) this node."""
        dependents = []
        for edge in self.memory_edges:
            target = edge.get("target") or edge.get("to")
            source = edge.get("source") or edge.get("from")
            if target == node_key and source:
                dependents.append(source)
        return list(set(dependents))

    # ──────────────────────────────────────────
    # Pattern Analysis (Task 9.2)
    # ──────────────────────────────────────────

    def _analyze_patterns(self) -> dict:
        """Analyze recurring patterns in the graph."""
        from collections import Counter

        layers: dict = {}
        names = []
        complexities = []

        for node in self.memory_nodes:
            layer = node.get("layer") or "unknown"
            layers[layer] = layers.get(layer, 0) + 1

            name = node.get("name") or ""
            if name:
                names.append(name)

            c = node.get("complexity")
            if c is not None:
                try:
                    complexities.append(float(c))
                except (TypeError, ValueError):
                    pass

        # Naming patterns: common prefixes/suffixes
        prefix_counter: Counter = Counter()
        suffix_counter: Counter = Counter()
        for name in names:
            if len(name) >= 4:
                prefix_counter[name[:4]] += 1
                suffix_counter[name[-4:]] += 1

        naming_patterns = {
            "common_prefixes": [p for p, _ in prefix_counter.most_common(5)],
            "common_suffixes": [s for s, _ in suffix_counter.most_common(5)],
        }

        avg_complexity = (sum(complexities) / len(complexities)) if complexities else 0.0

        # Top 5 nodes by hotspot_score
        sorted_nodes = sorted(
            [n for n in self.memory_nodes if n.get("namespace_key")],
            key=lambda n: float(n.get("hotspot_score") or 0),
            reverse=True,
        )
        example_nodes = sorted_nodes[:5]

        return {
            "layers": layers,
            "naming_patterns": naming_patterns,
            "avg_complexity": round(avg_complexity, 2),
            "example_nodes": example_nodes,
        }

    # ──────────────────────────────────────────
    # Ollama Helpers
    # ──────────────────────────────────────────

    async def _call_ollama_refactor(self, context: str, original_code: str) -> str:
        prompt = (
            f"{context}\n\n"
            "Com base nos problemas identificados, gere o código refatorado em Python/Java/TypeScript "
            "(mesma linguagem do original). Retorne APENAS o código refatorado, sem explicações.\n\n"
            f"Código original:\n```\n{original_code}\n```\n\n"
            "Código refatorado:"
        )
        return await self._ollama_generate(prompt)

    async def _call_ollama_tests(self, node: dict, suggested_code: str) -> str:
        name = node.get("name", "Component")
        prompt = (
            f"Gere casos de teste unitários para o seguinte código refatorado do componente '{name}'.\n"
            "Use pytest (Python) ou Jest (TypeScript/JavaScript) conforme a linguagem.\n"
            "Retorne APENAS o código de teste, sem explicações.\n\n"
            f"Código:\n```\n{suggested_code}\n```\n\n"
            "Testes unitários:"
        )
        return await self._ollama_generate(prompt)

    async def _call_ollama_architecture(self, context: str) -> str:
        return await self._ollama_generate(context)

    async def _ollama_generate(self, prompt: str) -> str:
        payload = {
            "model": self.complex_model,
            "prompt": prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.ollama_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()

    # ──────────────────────────────────────────
    # Context Builders
    # ──────────────────────────────────────────

    def _build_node_context(self, node: dict, problems: list, dependents: list) -> str:
        lines = [
            f"Nó: {node.get('name')} (namespace_key: {node.get('namespace_key')})",
            f"Layer: {node.get('layer')}",
            f"Complexidade: {node.get('complexity')}",
            f"WMC: {node.get('wmc')}",
            f"CBO: {node.get('cbo')}",
            f"In-degree: {node.get('in_degree')}, Out-degree: {node.get('out_degree')}",
            f"Arquivo: {node.get('file')}",
            "",
            "Problemas identificados:",
        ]
        for p in problems:
            lines.append(f"  - {p}")
        lines.append(f"\nDependentes afetados ({len(dependents)}): {', '.join(dependents[:5])}")
        return "\n".join(lines)

    def _build_architecture_context(self, description: str, patterns: dict) -> str:
        layers_str = ", ".join(f"{k}={v}" for k, v in patterns.get("layers", {}).items())
        naming = patterns.get("naming_patterns", {})
        prefixes = ", ".join(naming.get("common_prefixes", []))
        suffixes = ", ".join(naming.get("common_suffixes", []))
        examples = [n.get("name", "") for n in patterns.get("example_nodes", [])]

        return (
            f"Você é um arquiteto de software analisando o grafo de dependências do projeto.\n\n"
            f"Nova funcionalidade solicitada: {description}\n\n"
            f"Padrões do grafo atual:\n"
            f"  - Distribuição de camadas: {layers_str}\n"
            f"  - Prefixos comuns: {prefixes}\n"
            f"  - Sufixos comuns: {suffixes}\n"
            f"  - Complexidade média: {patterns.get('avg_complexity')}\n"
            f"  - Exemplos de nós de referência: {', '.join(examples)}\n\n"
            "Sugira como implementar a nova funcionalidade seguindo os padrões arquiteturais existentes. "
            "Inclua: camada recomendada, nomenclatura, dependências esperadas e estrutura de classes/módulos."
        )

    def _estimate_effort(self, problems: list, dependents_count: int) -> str:
        score = len(problems) + (dependents_count // 3)
        if score <= 1:
            return "baixo"
        elif score <= 3:
            return "médio"
        else:
            return "alto"
