"""
SemanticAnalyzer — Uses qwen3-coder-next to produce a natural-language impact analysis.

Requirements: 8.1–8.6
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

import httpx

logger = logging.getLogger("insightgraph")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_COMPLEX_MODEL = os.getenv("OLLAMA_COMPLEX_MODEL", "qwen3-coder-next:q4_K_M")
# Fallback model used when the complex model returns a server error (e.g. OOM)
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen2.5-coder:7b")

_REQUIRED_FIELDS = {"summary", "risk_level", "breaking_changes", "migration_steps", "estimated_effort"}
_VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_MAX_RETRIES = 2          # up to 2 additional attempts after the first (3 total)
_MAX_TOKENS = 8000        # approximate token budget for source snippets


@dataclass
class SemanticAnalysis:
    summary: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    breaking_changes: list[str]
    migration_steps: list[str]
    estimated_effort: str


class SemanticAnalyzer:
    """
    Sends a ChangeDescriptor + AffectedSet to qwen3-coder-next and returns
    a structured SemanticAnalysis.

    Requirements: 8.1–8.6
    """

    def __init__(self, ollama_url: str = OLLAMA_URL, model: str = OLLAMA_COMPLEX_MODEL):
        self._ollama_url = ollama_url
        self._model = model

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def analyze_impact(
        self,
        change,           # ChangeDescriptor
        affected_set,     # AffectedSet
        source_snippets: dict[str, str],  # ns_key → source code
    ) -> Optional[SemanticAnalysis]:
        """
        Call qwen3-coder-next with the change context and return SemanticAnalysis.

        Retries up to 2 additional times if the JSON response is missing required fields.
        Returns None if Ollama is unavailable or all retries fail.

        Requirements: 8.1–8.6
        """
        prompt = self._build_prompt(change, affected_set, source_snippets)
        current_model = self._model

        for attempt in range(_MAX_RETRIES + 1):
            try:
                raw = await self._call_ollama(prompt, model=current_model)
                result = self._parse_response(raw)
                if result is not None:
                    return result

                # Missing fields — build correction prompt for next attempt
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "SemanticAnalyzer: missing fields in attempt %d, retrying...", attempt + 1
                    )
                    prompt = self._build_correction_prompt(prompt, raw)

            except httpx.ConnectError:
                logger.warning("SemanticAnalyzer: cannot connect to Ollama at %s", self._ollama_url)
                return None
            except httpx.HTTPStatusError as e:
                # 500 usually means OOM / model not loaded — try fallback model once
                if e.response.status_code == 500 and current_model != OLLAMA_FALLBACK_MODEL:
                    logger.warning(
                        "SemanticAnalyzer: model %s returned 500, switching to fallback %s",
                        current_model, OLLAMA_FALLBACK_MODEL,
                    )
                    current_model = OLLAMA_FALLBACK_MODEL
                    continue
                logger.warning("SemanticAnalyzer HTTP error on attempt %d: %s", attempt + 1, e)
                if attempt >= _MAX_RETRIES:
                    return None
            except Exception as e:
                logger.warning("SemanticAnalyzer error on attempt %d: %s", attempt + 1, e)
                if attempt >= _MAX_RETRIES:
                    return None

        logger.warning("SemanticAnalyzer: all attempts failed, returning None")
        return None

    # ──────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────

    def _build_prompt(self, change, affected_set, source_snippets: dict[str, str]) -> str:
        """Build the initial analysis prompt, capped at ~_MAX_TOKENS chars."""
        # Collect DIRECT items for source snippets (highest priority)
        direct_keys = [
            item.namespace_key
            for item in affected_set.items
            if item.category == "DIRECT"
        ]

        snippets_text = ""
        budget = _MAX_TOKENS
        for key in direct_keys:
            snippet = source_snippets.get(key, "")
            if not snippet:
                continue
            chunk = f"\n// {key}\n{snippet[:500]}\n"
            if len(snippets_text) + len(chunk) > budget:
                break
            snippets_text += chunk

        affected_summary = "\n".join(
            f"- [{item.category}] {item.namespace_key} (confidence={item.confidence_score})"
            for item in affected_set.items[:50]
        )

        return f"""You are a senior software architect. Analyze the following proposed code change and its impact.

## Change Descriptor
- change_type: {change.change_type}
- target: {change.target_key}
- parameter_name: {change.parameter_name or 'N/A'}
- old_type: {change.old_type or 'N/A'}
- new_type: {change.new_type or 'N/A'}

## Affected Artefacts ({affected_set.analysis_metadata.total_affected} total)
{affected_summary}

## Source Code Snippets (DIRECT impacts)
{snippets_text or '(no snippets available)'}

Return ONLY a valid JSON object with exactly these fields (no markdown, no explanation):
{{
  "summary": "executive summary of the impact",
  "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
  "breaking_changes": ["list of breaking changes"],
  "migration_steps": ["ordered list of migration steps"],
  "estimated_effort": "e.g. 2-4 hours"
}}"""

    def _build_correction_prompt(self, original_prompt: str, bad_response: str) -> str:
        """Build a correction prompt when required fields are missing."""
        return (
            original_prompt
            + f"\n\nYour previous response was:\n{bad_response[:500]}\n\n"
            "It was missing required fields. Return ONLY the JSON object with ALL of these fields: "
            "summary, risk_level, breaking_changes, migration_steps, estimated_effort."
        )

    async def _call_ollama(self, prompt: str, model: str | None = None) -> str:
        """Send prompt to Ollama and return raw response text."""
        use_model = model or self._model
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 1500},
                },
            )
            response.raise_for_status()
            return response.json().get("response", "")

    def _parse_response(self, raw: str) -> Optional[SemanticAnalysis]:
        """
        Extract and validate JSON from raw Ollama response.
        Returns SemanticAnalysis if all required fields present, else None.

        Requirements: 8.2, 8.3
        """
        # Try direct JSON parse
        parsed = None
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                parsed = json.loads(raw[json_start:json_end])
            except json.JSONDecodeError:
                pass

        # Regex fallback
        if parsed is None:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if parsed is None:
            return None

        # Validate required fields
        missing = _REQUIRED_FIELDS - set(parsed.keys())
        if missing:
            logger.warning("SemanticAnalyzer: missing fields %s", missing)
            return None

        risk = str(parsed.get("risk_level", "MEDIUM")).upper()
        if risk not in _VALID_RISK_LEVELS:
            risk = "MEDIUM"

        return SemanticAnalysis(
            summary=str(parsed.get("summary", "")),
            risk_level=risk,  # type: ignore[arg-type]
            breaking_changes=list(parsed.get("breaking_changes") or []),
            migration_steps=list(parsed.get("migration_steps") or []),
            estimated_effort=str(parsed.get("estimated_effort", "unknown")),
        )
