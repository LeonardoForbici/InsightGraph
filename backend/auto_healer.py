"""Auto Healer engine: detect bug patterns, suggest fixes, tests and docs updates."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Optional

import httpx

from ollama_runtime import OllamaRuntime, OllamaServiceError
from state_store import LocalStateStore

logger = logging.getLogger("insightgraph.auto_healer")


class AutoHealer:
    def __init__(
        self,
        state_store: LocalStateStore,
        ollama_url: str,
        model: str,
        ollama_runtime: OllamaRuntime | None = None,
    ):
        self.state_store = state_store
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.ollama_runtime = ollama_runtime

    def detect_bug_patterns(
        self,
        changes: list[dict[str, Any]],
        commit_history: Optional[list[dict[str, Any]]] = None,
        pr_history: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        commit_history = commit_history or []
        pr_history = pr_history or []
        patterns: list[dict[str, Any]] = []
        for change in changes:
            file_path = str(change.get("file") or change.get("path") or "")
            diff = str(change.get("diff") or "")
            lowered = diff.lower()
            category = None
            confidence = 0.4
            if "null" in lowered and ("." in diff or "->" in diff):
                category = "null-reference"
                confidence = 0.72
            elif "timeout" in lowered or "retry" in lowered:
                category = "transient-failure"
                confidence = 0.64
            elif "sql" in lowered and ("concat(" in lowered or "+" in lowered):
                category = "unsafe-query-construction"
                confidence = 0.78
            elif re.search(r"except\s*:\s*pass", diff):
                category = "silent-failure"
                confidence = 0.69
            if not category:
                continue
            recent_related = sum(
                1
                for item in commit_history[-100:]
                if file_path and file_path in str(item.get("files") or item.get("message") or "")
            )
            failed_prs = sum(
                1
                for pr in pr_history[-100:]
                if str(pr.get("status") or "").lower() in {"failed", "failure", "error"}
            )
            score = min(100.0, confidence * 100.0 + recent_related * 2.5 + failed_prs * 1.5)
            patterns.append(
                {
                    "id": str(uuid.uuid4()),
                    "pattern": category,
                    "file_path": file_path,
                    "confidence": round(confidence, 3),
                    "risk_score": round(score, 2),
                    "evidence": diff[:1200],
                    "created_at": time.time(),
                }
            )
        return patterns

    async def suggest_fix(self, bug_pattern: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "You are a principal software engineer.\n"
            "Given this bug pattern, produce a compact JSON with keys: root_cause, fix_plan, patch_outline.\n"
            f"Pattern: {json.dumps(bug_pattern, ensure_ascii=False)}"
        )
        generated = await self._generate_with_ollama(prompt)
        return {
            "pattern_id": bug_pattern.get("id"),
            "file_path": bug_pattern.get("file_path"),
            "suggestion": generated,
            "created_at": time.time(),
        }

    async def generate_tests(self, fragility_point: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Generate test code and test cases for the fragility point.\n"
            "Return compact markdown with sections: strategy, unit tests, integration tests.\n"
            f"Fragility point: {json.dumps(fragility_point, ensure_ascii=False)}"
        )
        content = await self._generate_with_ollama(prompt)
        return {
            "fragility_point": fragility_point,
            "generated_tests": content,
            "created_at": time.time(),
        }

    async def suggest_refactor(self, node_profile: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Suggest refactoring actions prioritizing low-risk/high-impact wins.\n"
            "Return JSON with keys: quick_wins, medium_refactors, long_term.\n"
            f"Node profile: {json.dumps(node_profile, ensure_ascii=False)}"
        )
        content = await self._generate_with_ollama(prompt)
        return {
            "node_profile": node_profile,
            "recommendation": content,
            "created_at": time.time(),
        }

    async def generate_doc_updates(self, changed_docs: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = (
            "Detect stale docs and propose updates.\n"
            "Return markdown bullet list with updated sections and suggested new text.\n"
            f"Changed docs context: {json.dumps(changed_docs, ensure_ascii=False)}"
        )
        content = await self._generate_with_ollama(prompt)
        return {
            "updates": content,
            "commit_draft": {
                "title": "docs: auto-healer documentation refresh",
                "body": "Generated by Auto Healer based on source-code drift.",
            },
            "created_at": time.time(),
        }

    async def _generate_with_ollama(self, prompt: str) -> str:
        try:
            if self.ollama_runtime is not None:
                data = await self.ollama_runtime.generate(
                    model=self.model,
                    prompt=prompt,
                    timeout=18.0,
                    retries=1,
                    keep_alive="5m",
                )
                return str(data.get("response") or "").strip() or "No response."
            url = f"{self.ollama_url}/api/generate"
            payload = {"model": self.model, "prompt": prompt, "stream": False}
            async with httpx.AsyncClient(timeout=18.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return str(data.get("response") or "").strip() or "No response."
        except OllamaServiceError as exc:
            logger.warning("AutoHealer fallback due to Ollama runtime error: %s", exc)
            return "Auto-healer fallback: validate null checks, input validation, and error handling; then add regression tests."
        except Exception as exc:
            logger.warning("AutoHealer fallback due to Ollama error: %s", exc)
            return "Auto-healer fallback: validate null checks, input validation, and error handling; then add regression tests."
