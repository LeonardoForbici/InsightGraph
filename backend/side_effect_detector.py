"""
SideEffectDetector — Detects silent business-logic side effects of code changes.

Extracts Business_Rule_Nodes from source code (explicit comments/annotations or
inferred via Ollama) and crosses them with the Affected_Set to surface violations.

Requirements: 3.1–3.8, 7.2
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger("insightgraph")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_COMPLEX_MODEL = os.getenv("OLLAMA_COMPLEX_MODEL", "qwen3-coder-next:q4_K_M")
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen2.5-coder:7b")

# Keywords that indicate retroactive / historical data operations
_RETROACTIVE_KEYWORDS = {
    "retroactive", "retroativo", "retroativa", "historical", "historico",
    "historica", "histórico", "histórica", "past", "previous", "anterior",
    "backdate", "back-date", "reprocess", "reprocessar", "competencia",
    "competência", "periodo", "período", "period", "fiscal", "fechamento",
}

# Date-related parameter patterns
_DATE_PARAM_PATTERN = re.compile(
    r"\b(dt_|data_|date_|p_date|p_dt|p_data|dat_|dta_|start_date|end_date|"
    r"data_inicio|data_fim|data_competencia|data_referencia|periodo|period)\b",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

@dataclass
class BusinessRuleNode:
    rule_key: str
    rule_text: str
    rule_type: str          # "SILENT_LOGIC_FAILURE" | "DOMAIN_RESTRICTION" | "RETROACTIVE_RULE_VIOLATION"
    artifact_key: str
    inferred: bool
    confidence_score: int


@dataclass
class SideEffect:
    artifact_key: str
    artifact_name: str
    effect_type: str        # "SILENT_LOGIC_FAILURE" | "DOMAIN_RESTRICTION" | "RETROACTIVE_RULE_VIOLATION"
    rule_violated: str
    side_effect_risk: bool
    inferred: bool
    confidence_score: int


# ──────────────────────────────────────────────
# Regex patterns for explicit rule extraction
# ──────────────────────────────────────────────

# Java/TypeScript: // BUSINESS RULE: <text>
_JAVA_RULE_PATTERN = re.compile(
    r"//\s*BUSINESS\s+RULE\s*:\s*(.+)",
    re.IGNORECASE,
)

# PL/SQL: --RULE: <text>
_PLSQL_RULE_PATTERN = re.compile(
    r"--\s*RULE\s*:\s*(.+)",
    re.IGNORECASE,
)

# Java annotation: @BusinessRule (optionally with value)
_ANNOTATION_PATTERN = re.compile(
    r'@BusinessRule\s*(?:\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']?\s*\))?',
    re.IGNORECASE,
)


class SideEffectDetector:
    """
    Detects silent business-logic side effects by extracting Business_Rule_Nodes
    and crossing them with the Affected_Set.

    Requirements: 3.1–3.8, 7.2
    """

    def __init__(
        self,
        neo4j_service,
        memory_nodes: dict,
        memory_edges: list,
        semantic_analyzer,
    ):
        self._neo4j = neo4j_service
        self._memory_nodes = memory_nodes   # {node_key: {"labels": [...], "properties": {...}}}
        self._memory_edges = memory_edges   # [{"from": key, "to": key, "type": rel_type, ...}]
        self._semantic_analyzer = semantic_analyzer

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def detect(self, change: dict, affected_set: list[str]) -> list[SideEffect]:
        """
        Detect side effects for a change, crossing business rules with the Affected_Set.

        Args:
            change: dict with keys artifact_key, change_type, old_value, new_value
            affected_set: list of artifact_keys (strings)

        Returns:
            list of SideEffect

        Requirements: 3.1–3.4, 3.7, 3.8
        """
        artifact_key: str = change.get("artifact_key", "")
        source_code: str = change.get("source_code", "")

        # If source_code not in change, try to retrieve from memory/neo4j
        if not source_code:
            source_code = self._get_source_code(artifact_key)

        # Extract explicit business rules from the changed artifact
        rules = self.extract_business_rules(source_code, artifact_key)

        # If no explicit rules found, infer via Ollama
        if not rules and source_code:
            rules = await self._infer_rules_via_ollama(source_code, artifact_key)

        # Persist rules to Neo4j (or memory fallback)
        if rules:
            self._persist_rules(rules)

        side_effects: list[SideEffect] = []

        # Cross rules with affected_set
        for affected_key in affected_set:
            if affected_key == artifact_key:
                continue

            affected_name = self._get_artifact_name(affected_key)

            for rule in rules:
                # Check for retroactive violations first
                retro_effects = self._check_retroactive_violation(change, [rule])
                if retro_effects:
                    for effect in retro_effects:
                        # Attach to the affected artifact
                        side_effects.append(SideEffect(
                            artifact_key=affected_key,
                            artifact_name=affected_name,
                            effect_type="RETROACTIVE_RULE_VIOLATION",
                            rule_violated=rule.rule_text,
                            side_effect_risk=True,
                            inferred=rule.inferred,
                            confidence_score=rule.confidence_score,
                        ))
                    continue

                # Classify as DOMAIN_RESTRICTION or SILENT_LOGIC_FAILURE
                effect_type = self._classify_effect_type(change, rule)
                side_effects.append(SideEffect(
                    artifact_key=affected_key,
                    artifact_name=affected_name,
                    effect_type=effect_type,
                    rule_violated=rule.rule_text,
                    side_effect_risk=True,
                    inferred=rule.inferred,
                    confidence_score=rule.confidence_score,
                ))

        return side_effects

    def extract_business_rules(
        self, source_code: str, artifact_key: str
    ) -> list[BusinessRuleNode]:
        """
        Extract explicit business rules from source code using regex patterns.

        Patterns:
        - // BUSINESS RULE: <text>  (Java/TypeScript)
        - --RULE: <text>            (PL/SQL)
        - @BusinessRule             (Java annotation)

        Requirements: 3.1, 3.5
        """
        rules: list[BusinessRuleNode] = []
        index = 0

        # Java/TypeScript comments: // BUSINESS RULE: <text>
        for match in _JAVA_RULE_PATTERN.finditer(source_code):
            rule_text = match.group(1).strip()
            rule_key = f"{artifact_key}::rule::{index}"
            rule_type = self._classify_rule_type(rule_text, source_code)
            rules.append(BusinessRuleNode(
                rule_key=rule_key,
                rule_text=rule_text,
                rule_type=rule_type,
                artifact_key=artifact_key,
                inferred=False,
                confidence_score=100,
            ))
            index += 1

        # PL/SQL comments: --RULE: <text>
        for match in _PLSQL_RULE_PATTERN.finditer(source_code):
            rule_text = match.group(1).strip()
            rule_key = f"{artifact_key}::rule::{index}"
            rule_type = self._classify_rule_type(rule_text, source_code)
            rules.append(BusinessRuleNode(
                rule_key=rule_key,
                rule_text=rule_text,
                rule_type=rule_type,
                artifact_key=artifact_key,
                inferred=False,
                confidence_score=100,
            ))
            index += 1

        # Java annotations: @BusinessRule
        for match in _ANNOTATION_PATTERN.finditer(source_code):
            annotation_value = match.group(1)
            rule_text = annotation_value.strip() if annotation_value else f"@BusinessRule on {artifact_key}"
            rule_key = f"{artifact_key}::rule::{index}"
            rule_type = self._classify_rule_type(rule_text, source_code)
            rules.append(BusinessRuleNode(
                rule_key=rule_key,
                rule_text=rule_text,
                rule_type=rule_type,
                artifact_key=artifact_key,
                inferred=False,
                confidence_score=100,
            ))
            index += 1

        return rules

    def _check_retroactive_violation(
        self, change: dict, rules: list[BusinessRuleNode]
    ) -> list[SideEffect]:
        """
        Detect RETROACTIVE_RULE_VIOLATION: changes that alter behavior for historical
        data operations (date parameters, period filters, retroactive keywords).

        Requirements: 3.3, 3.8
        """
        side_effects: list[SideEffect] = []

        artifact_key = change.get("artifact_key", "")
        old_value = str(change.get("old_value", ""))
        new_value = str(change.get("new_value", ""))
        change_type = str(change.get("change_type", ""))

        # Check if the change involves date/period parameters
        has_date_param = bool(
            _DATE_PARAM_PATTERN.search(old_value)
            or _DATE_PARAM_PATTERN.search(new_value)
            or _DATE_PARAM_PATTERN.search(artifact_key)
        )

        # Check if change_type suggests parameter restriction
        is_restrictive_change = change_type in {
            "change_procedure_param",
            "change_column_type",
            "rename_parameter",
            "remove_parameter",
        }

        for rule in rules:
            rule_text_lower = rule.rule_text.lower()

            # Check for retroactive keywords in rule text
            has_retroactive_keyword = any(
                kw in rule_text_lower for kw in _RETROACTIVE_KEYWORDS
            )

            # Check for date-related content in rule text
            has_date_in_rule = bool(_DATE_PARAM_PATTERN.search(rule.rule_text))

            if has_retroactive_keyword or (has_date_param and is_restrictive_change) or has_date_in_rule:
                artifact_name = self._get_artifact_name(artifact_key)
                side_effects.append(SideEffect(
                    artifact_key=artifact_key,
                    artifact_name=artifact_name,
                    effect_type="RETROACTIVE_RULE_VIOLATION",
                    rule_violated=rule.rule_text,
                    side_effect_risk=True,
                    inferred=rule.inferred,
                    confidence_score=rule.confidence_score,
                ))

        return side_effects

    async def _infer_rules_via_ollama(
        self, source_code: str, artifact_key: str
    ) -> list[BusinessRuleNode]:
        """
        Infer implicit business rules from source code via Ollama.

        Primary model: configured OLLAMA_COMPLEX_MODEL (qwen3-coder-next)
        Fallback model: qwen2.5-coder:7b
        All inferred rules have inferred=True and confidence_score < 70.

        Requirements: 3.7
        """
        prompt = self._build_inference_prompt(source_code, artifact_key)
        current_model = OLLAMA_COMPLEX_MODEL

        for attempt in range(2):
            try:
                raw = await self._call_ollama(prompt, model=current_model)
                rules = self._parse_inferred_rules(raw, artifact_key)
                if rules:
                    return rules
                # Empty result — try fallback on second attempt
                if attempt == 0 and current_model != OLLAMA_FALLBACK_MODEL:
                    logger.warning(
                        "SideEffectDetector: no rules inferred by %s, trying fallback",
                        current_model,
                    )
                    current_model = OLLAMA_FALLBACK_MODEL

            except httpx.ConnectError:
                logger.warning(
                    "SideEffectDetector: cannot connect to Ollama at %s", OLLAMA_URL
                )
                return []
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 500 and current_model != OLLAMA_FALLBACK_MODEL:
                    logger.warning(
                        "SideEffectDetector: model %s returned 500, switching to fallback %s",
                        current_model,
                        OLLAMA_FALLBACK_MODEL,
                    )
                    current_model = OLLAMA_FALLBACK_MODEL
                    continue
                logger.warning("SideEffectDetector HTTP error: %s", e)
                return []
            except Exception as e:
                logger.warning("SideEffectDetector Ollama error: %s", e)
                return []

        return []

    def _persist_rules(self, rules: list[BusinessRuleNode]) -> None:
        """
        Persist Business_Rule_Node in Neo4j via MERGE with ENFORCES_RULE relationship.
        Falls back to memory if Neo4j is unavailable.

        Requirements: 3.5, 7.2
        """
        if self._neo4j and getattr(self._neo4j, "is_connected", False):
            try:
                self._persist_rules_neo4j(rules)
                return
            except Exception as e:
                logger.warning(
                    "SideEffectDetector: Neo4j persist failed, falling back to memory: %s", e
                )

        self._persist_rules_memory(rules)

    # ──────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────

    def _persist_rules_neo4j(self, rules: list[BusinessRuleNode]) -> None:
        """Write Business_Rule_Node nodes and ENFORCES_RULE relationships to Neo4j."""
        cypher = """
        MERGE (rule:Business_Rule_Node {namespace_key: $namespace_key})
        SET rule.rule_text        = $rule_text,
            rule.rule_type        = $rule_type,
            rule.inferred         = $inferred,
            rule.confidence_score = $confidence_score,
            rule.artifact_key     = $artifact_key
        WITH rule
        MATCH (artifact:Entity {namespace_key: $artifact_key})
        MERGE (artifact)-[:ENFORCES_RULE]->(rule)
        """
        for rule in rules:
            params = {
                "namespace_key": rule.rule_key,
                "rule_text": rule.rule_text,
                "rule_type": rule.rule_type,
                "inferred": rule.inferred,
                "confidence_score": rule.confidence_score,
                "artifact_key": rule.artifact_key,
            }
            try:
                # Support both py2neo (.graph.run) and custom neo4j_service (.query)
                if hasattr(self._neo4j, "graph"):
                    self._neo4j.graph.run(cypher, **params)
                else:
                    self._neo4j.query(cypher, params)
            except Exception as e:
                logger.warning("SideEffectDetector: failed to persist rule %s: %s", rule.rule_key, e)

    def _persist_rules_memory(self, rules: list[BusinessRuleNode]) -> None:
        """Store Business_Rule_Node in memory_nodes and ENFORCES_RULE in memory_edges."""
        for rule in rules:
            node_key = rule.rule_key
            self._memory_nodes[node_key] = {
                "labels": ["Business_Rule_Node"],
                "properties": {
                    "namespace_key": node_key,
                    "rule_text": rule.rule_text,
                    "rule_type": rule.rule_type,
                    "inferred": rule.inferred,
                    "confidence_score": rule.confidence_score,
                    "artifact_key": rule.artifact_key,
                },
            }
            self._memory_edges.append({
                "from": rule.artifact_key,
                "to": node_key,
                "type": "ENFORCES_RULE",
                "properties": {},
            })

    def _classify_rule_type(self, rule_text: str, source_code: str = "") -> str:
        """
        Classify a rule as RETROACTIVE_RULE_VIOLATION, DOMAIN_RESTRICTION,
        or SILENT_LOGIC_FAILURE based on its text content.
        """
        text_lower = rule_text.lower()

        # Check for retroactive/historical keywords
        if any(kw in text_lower for kw in _RETROACTIVE_KEYWORDS):
            return "RETROACTIVE_RULE_VIOLATION"

        # Check for domain restriction keywords
        domain_keywords = {
            "only", "must", "cannot", "not allowed", "restricted", "limit",
            "maximum", "minimum", "range", "valid", "invalid", "forbidden",
            "somente", "apenas", "nao pode", "não pode", "proibido", "restrito",
            "obrigatorio", "obrigatório", "permitido", "dominio", "domínio",
        }
        if any(kw in text_lower for kw in domain_keywords):
            return "DOMAIN_RESTRICTION"

        return "SILENT_LOGIC_FAILURE"

    def _classify_effect_type(self, change: dict, rule: BusinessRuleNode) -> str:
        """Determine the SideEffect effect_type based on change and rule."""
        change_type = change.get("change_type", "")

        # Parameter removal/restriction → DOMAIN_RESTRICTION
        if change_type in {"remove_parameter", "change_procedure_param", "change_column_type"}:
            return "DOMAIN_RESTRICTION"

        # Use the rule's own type as a hint
        if rule.rule_type in {"DOMAIN_RESTRICTION", "RETROACTIVE_RULE_VIOLATION"}:
            return rule.rule_type

        return "SILENT_LOGIC_FAILURE"

    def _get_source_code(self, artifact_key: str) -> str:
        """Retrieve source code for an artifact from memory_nodes."""
        node = self._memory_nodes.get(artifact_key, {})
        props = node.get("properties", {}) if isinstance(node, dict) else {}
        return props.get("source_code", "") or props.get("source", "")

    def _get_artifact_name(self, artifact_key: str) -> str:
        """Retrieve the display name for an artifact."""
        node = self._memory_nodes.get(artifact_key, {})
        if isinstance(node, dict):
            props = node.get("properties", {})
            name = props.get("name") or props.get("namespace_key")
            if name:
                return name
        # Fallback: last segment of the key
        return artifact_key.split("::")[-1] if "::" in artifact_key else artifact_key

    def _build_inference_prompt(self, source_code: str, artifact_key: str) -> str:
        """Build the Ollama prompt for inferring business rules."""
        snippet = source_code[:3000]  # cap to avoid token overflow
        return f"""You are a senior software architect analyzing source code for implicit business rules.

Analyze the following source code from artifact "{artifact_key}" and identify any implicit business rules,
constraints, or domain restrictions that are NOT explicitly documented but are enforced by the code logic.

Source code:
```
{snippet}
```

Return ONLY a valid JSON array of objects with exactly these fields (no markdown, no explanation):
[
  {{
    "rule_text": "description of the implicit business rule",
    "rule_type": "SILENT_LOGIC_FAILURE | DOMAIN_RESTRICTION | RETROACTIVE_RULE_VIOLATION"
  }}
]

If no implicit rules are found, return an empty array: []"""

    async def _call_ollama(self, prompt: str, model: str) -> str:
        """Send prompt to Ollama and return raw response text."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 1000},
                },
            )
            response.raise_for_status()
            return response.json().get("response", "")

    def _parse_inferred_rules(
        self, raw: str, artifact_key: str
    ) -> list[BusinessRuleNode]:
        """
        Parse Ollama response into BusinessRuleNode list.
        All inferred rules get inferred=True and confidence_score < 70.
        """
        parsed = None

        # Try direct JSON parse
        arr_start = raw.find("[")
        arr_end = raw.rfind("]") + 1
        if arr_start >= 0 and arr_end > arr_start:
            try:
                parsed = json.loads(raw[arr_start:arr_end])
            except json.JSONDecodeError:
                pass

        # Regex fallback
        if parsed is None:
            match = re.search(r"\[[\s\S]*\]", raw)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if not parsed or not isinstance(parsed, list):
            return []

        rules: list[BusinessRuleNode] = []
        valid_types = {"SILENT_LOGIC_FAILURE", "DOMAIN_RESTRICTION", "RETROACTIVE_RULE_VIOLATION"}

        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            rule_text = str(item.get("rule_text", "")).strip()
            if not rule_text:
                continue
            rule_type = str(item.get("rule_type", "SILENT_LOGIC_FAILURE")).upper()
            if rule_type not in valid_types:
                rule_type = "SILENT_LOGIC_FAILURE"

            rules.append(BusinessRuleNode(
                rule_key=f"{artifact_key}::rule::{i}",
                rule_text=rule_text,
                rule_type=rule_type,
                artifact_key=artifact_key,
                inferred=True,
                confidence_score=60,  # always < 70 for inferred rules (Requirement 3.7)
            ))

        return rules
