"""
PR Bot — InsightGraph GitHub Actions integration.

Analyzes Pull Requests by calling the InsightGraph backend API and posting
a structured comment with impact score, affected services, and antipatterns.

Usage (via GitHub Actions):
    python backend/pr_bot.py

Environment variables:
    INSIGHTGRAPH_URL   — Base URL of the InsightGraph backend (e.g. http://localhost:8000)
    GITHUB_TOKEN       — GitHub token with write access to PR comments
    GITHUB_REPOSITORY  — Repository in "owner/repo" format
    PR_NUMBER          — Pull Request number
    CHANGED_FILES      — Space-separated list of changed file paths
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger("pr_bot")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

@dataclass
class AffectedSet:
    """Simplified view of the impact analysis result used by the bot."""
    items: list[dict] = field(default_factory=list)
    analysis_metadata: dict = field(default_factory=dict)

    @property
    def affected_count(self) -> int:
        return len(self.items)

    @property
    def max_depth(self) -> int:
        """Return the maximum call-chain depth across all affected items."""
        if not self.items:
            return 0
        return max(
            (len(item.get("call_chain", [])) - 1 for item in self.items),
            default=0,
        )


@dataclass
class PRComment:
    """Structured PR comment produced by the bot."""
    score: int
    affected_nodes: list[dict]
    antipatterns: dict
    body: str


# ──────────────────────────────────────────────
# PRBot
# ──────────────────────────────────────────────

BOT_MARKER = "<!-- insightgraph-pr-bot -->"


class PRBot:
    """
    Integrates InsightGraph analysis into GitHub Pull Requests.

    Workflow:
      1. POST /api/scan with only the changed files (incremental)
      2. POST /api/impact/analyze to get the affected set
      3. GET  /api/antipatterns to get antipatterns
      4. Compute impact score
      5. Build comment body
      6. POST or PATCH the PR comment (upsert)
    """

    def __init__(self, api_url: str, github_token: str, repo: str):
        self.api_url = api_url.rstrip("/")
        self.github_token = github_token
        self.repo = repo  # "owner/repo"

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    async def handle_pr_event(
        self, pr_number: int, changed_files: list[str]
    ) -> PRComment:
        """
        Orchestrate the full PR analysis flow.

        Steps:
          1. Incremental scan of changed files
          2. Impact analysis
          3. Antipatterns fetch
          4. Score computation
          5. Comment upsert
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            # 1. Incremental scan — only the changed files
            logger.info("Scanning %d changed file(s)…", len(changed_files))
            await self._call_scan(client, changed_files)

            # 2. Impact analysis — use the first changed file as the target key
            #    (heuristic: derive namespace_key from file path)
            affected_set = await self._call_impact_analyze(client, changed_files)

            # 3. Antipatterns
            antipatterns = await self._call_antipatterns(client)

        # 4. Score
        score = await self.compute_impact_score(affected_set, antipatterns)

        # 5. Build comment body
        body = self._build_comment_body(score, affected_set, antipatterns)

        # 6. Upsert comment
        await self.post_or_update_comment(pr_number, body)

        return PRComment(
            score=score,
            affected_nodes=affected_set.items,
            antipatterns=antipatterns,
            body=body,
        )

    async def compute_impact_score(
        self, affected_set: AffectedSet, antipatterns: dict
    ) -> int:
        """
        Compute a numeric impact score in [0, 100].

        Formula:
            score = min(100, (affected_count * 2) + (max_depth * 5) + (antipattern_count * 10))

        Validates: Requirements 1.4
        """
        affected_count = affected_set.affected_count
        max_depth = affected_set.max_depth
        antipattern_count = _count_antipatterns(antipatterns)

        raw = (affected_count * 2) + (max_depth * 5) + (antipattern_count * 10)
        score = min(100, raw)
        # Guarantee lower bound (raw is always >= 0 for valid inputs)
        score = max(0, score)
        return score

    async def post_or_update_comment(self, pr_number: int, body: str) -> None:
        """
        Upsert a bot comment on the PR.

        - Searches for an existing comment with BOT_MARKER.
        - If found: PATCH (update) it.
        - If not found: POST (create) a new one.

        Validates: Requirements 1.8
        """
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        base = f"https://api.github.com/repos/{self.repo}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Search for existing bot comment
            existing_id = await self._find_existing_comment(
                client, headers, base, pr_number
            )

            if existing_id:
                # PATCH — update existing comment
                url = f"{base}/issues/comments/{existing_id}"
                resp = await client.patch(url, headers=headers, json={"body": body})
                resp.raise_for_status()
                logger.info("Updated existing PR comment (id=%d)", existing_id)
            else:
                # POST — create new comment
                url = f"{base}/issues/{pr_number}/comments"
                resp = await client.post(url, headers=headers, json={"body": body})
                resp.raise_for_status()
                logger.info("Created new PR comment")

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    async def _call_scan(
        self, client: httpx.AsyncClient, changed_files: list[str]
    ) -> None:
        """POST /api/scan with only the changed files."""
        url = f"{self.api_url}/api/scan"
        try:
            resp = await client.post(url, json={"paths": changed_files})
            resp.raise_for_status()
            logger.info("Scan triggered successfully")
        except httpx.HTTPError as exc:
            logger.warning("Scan request failed: %s", exc)
            # Non-fatal — continue with whatever is in the graph

    async def _call_impact_analyze(
        self, client: httpx.AsyncClient, changed_files: list[str]
    ) -> AffectedSet:
        """POST /api/impact/analyze and return an AffectedSet."""
        url = f"{self.api_url}/api/impact/analyze"
        # Derive a target_key heuristic from the first changed file
        target_key = _file_to_namespace_key(changed_files[0]) if changed_files else ""
        payload = {
            "change_type": "change_method_signature",
            "target_key": target_key,
            "max_depth": 5,
        }
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            metadata = data.get("analysis_metadata", {})
            return AffectedSet(items=items, analysis_metadata=metadata)
        except httpx.HTTPError as exc:
            logger.warning("Impact analysis request failed: %s", exc)
            return AffectedSet()

    async def _call_antipatterns(self, client: httpx.AsyncClient) -> dict:
        """GET /api/antipatterns and return the antipatterns dict."""
        url = f"{self.api_url}/api/antipatterns"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Antipatterns request failed: %s", exc)
            return {}

    async def _find_existing_comment(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        base: str,
        pr_number: int,
    ) -> Optional[int]:
        """
        Search for an existing bot comment on the PR.

        Returns the comment ID if found, else None.
        Uses GET /repos/{repo}/issues/{pr_number}/comments (paginated).
        """
        url = f"{base}/issues/{pr_number}/comments"
        page = 1
        while True:
            resp = await client.get(
                url,
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            comments = resp.json()
            if not comments:
                break
            for comment in comments:
                if BOT_MARKER in comment.get("body", ""):
                    return comment["id"]
            if len(comments) < 100:
                break
            page += 1
        return None

    def _build_comment_body(
        self,
        score: int,
        affected_set: AffectedSet,
        antipatterns: dict,
    ) -> str:
        """Build the markdown body for the PR comment."""
        lines: list[str] = [BOT_MARKER, "## 🔍 InsightGraph — Impact Analysis", ""]

        # Score badge
        badge_color = "brightgreen" if score < 40 else ("yellow" if score < 70 else "red")
        lines.append(
            f"**Impact Score:** ![score](https://img.shields.io/badge/score-{score}-{badge_color})"
        )
        lines.append("")

        # Affected services / modules
        lines.append("### 📦 Affected Services & Modules")
        if affected_set.items:
            for item in affected_set.items[:20]:  # cap at 20 for readability
                name = item.get("name") or item.get("namespace_key", "unknown")
                category = item.get("category", "")
                confidence = item.get("confidence_score", 0)
                lines.append(f"- `{name}` — {category} (confidence: {confidence}%)")
            if len(affected_set.items) > 20:
                lines.append(
                    f"- _…and {len(affected_set.items) - 20} more affected nodes_"
                )
        else:
            lines.append("_No affected nodes detected._")
        lines.append("")

        # Risk alerts
        lines.append("### ⚠️ Risk Alerts")
        risk_items = _collect_risk_alerts(antipatterns)
        if risk_items:
            for alert in risk_items:
                lines.append(f"- {alert}")
        else:
            lines.append("_No risk alerts detected._")
        lines.append("")

        # Antipatterns detail
        lines.append("### 🐛 Antipatterns Detected")
        antipattern_count = _count_antipatterns(antipatterns)
        if antipattern_count > 0:
            for category, items in antipatterns.items():
                if isinstance(items, list) and items:
                    lines.append(f"**{category.replace('_', ' ').title()}** ({len(items)})")
                    for ap in items[:5]:
                        key = ap.get("key") or ap.get("namespace_key") or ap.get("name", "?")
                        lines.append(f"  - `{key}`")
                    if len(items) > 5:
                        lines.append(f"  - _…and {len(items) - 5} more_")
        else:
            lines.append("_No antipatterns detected._")
        lines.append("")

        # Metadata
        meta = affected_set.analysis_metadata
        if meta:
            elapsed = meta.get("elapsed_seconds", 0)
            lines.append(f"_Analysis completed in {elapsed:.2f}s_")

        return "\n".join(lines)


# ──────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────

def _count_antipatterns(antipatterns: dict) -> int:
    """Count total antipattern instances across all categories."""
    total = 0
    for items in antipatterns.values():
        if isinstance(items, list):
            total += len(items)
    return total


def _collect_risk_alerts(antipatterns: dict) -> list[str]:
    """Build a human-readable list of risk alerts from antipatterns."""
    alerts: list[str] = []
    high_risk_categories = {
        "circular_dependencies": "Circular dependency detected",
        "god_classes": "God class detected (high complexity)",
        "hardcoded_secrets": "Hardcoded secret detected",
        "sql_injection_risk": "SQL injection risk",
        "cloud_blockers": "Cloud blocker (disk I/O)",
        "architecture_violations": "Architecture layer violation",
    }
    for category, label in high_risk_categories.items():
        items = antipatterns.get(category, [])
        if isinstance(items, list) and items:
            for item in items[:3]:
                key = item.get("key") or item.get("namespace_key") or item.get("name", "?")
                alerts.append(f"**{label}**: `{key}`")
    return alerts


def _file_to_namespace_key(file_path: str) -> str:
    """
    Derive a heuristic namespace_key from a file path.

    e.g. "src/services/UserService.java" → "UserService"
    """
    import re
    name = os.path.splitext(os.path.basename(file_path))[0]
    # Remove non-alphanumeric characters except underscores
    name = re.sub(r"[^a-zA-Z0-9_]", "", name)
    return name


# ──────────────────────────────────────────────
# Error handling wrapper
# ──────────────────────────────────────────────

async def _run_with_error_handling(
    bot: PRBot, pr_number: int, changed_files: list[str]
) -> None:
    """
    Run the PR bot with graceful error handling.

    If the backend is unavailable or any error occurs:
      - Post an error comment on the PR
      - Exit with code 0 (never block the PR merge)

    Validates: Requirements 1.7
    """
    try:
        await bot.handle_pr_event(pr_number, changed_files)
    except Exception as exc:
        logger.error("PR bot failed: %s", exc)
        error_body = _build_error_comment(str(exc))
        try:
            await bot.post_or_update_comment(pr_number, error_body)
        except Exception as comment_exc:
            logger.error("Failed to post error comment: %s", comment_exc)
        # Always exit 0 — never block the PR merge
        sys.exit(0)


def _build_error_comment(reason: str) -> str:
    """Build an error comment body when the backend is unavailable."""
    return "\n".join([
        BOT_MARKER,
        "## 🔍 InsightGraph — Impact Analysis",
        "",
        "> ⚠️ **Analysis unavailable**",
        ">",
        f"> The InsightGraph backend could not complete the analysis: `{reason}`",
        ">",
        "> This does not block the PR merge. Please check the backend status and re-run if needed.",
    ])


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    api_url = os.environ.get("INSIGHTGRAPH_URL", "http://localhost:8000")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number_str = os.environ.get("PR_NUMBER", "0")
    changed_files_str = os.environ.get("CHANGED_FILES", "")

    if not github_token:
        logger.error("GITHUB_TOKEN is not set")
        sys.exit(0)

    if not repo:
        logger.error("GITHUB_REPOSITORY is not set")
        sys.exit(0)

    try:
        pr_number = int(pr_number_str)
    except ValueError:
        logger.error("PR_NUMBER is not a valid integer: %s", pr_number_str)
        sys.exit(0)

    changed_files = [f.strip() for f in changed_files_str.split() if f.strip()]
    if not changed_files:
        logger.warning("No changed files provided — skipping analysis")
        sys.exit(0)

    bot = PRBot(api_url=api_url, github_token=github_token, repo=repo)
    asyncio.run(_run_with_error_handling(bot, pr_number, changed_files))


if __name__ == "__main__":
    main()
