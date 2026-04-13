"""CI/CD webhook normalization and build status extraction."""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

logger = logging.getLogger("insightgraph.cicd")

BuildProvider = Literal["github_actions", "gitlab_ci", "jenkins"]


@dataclass
class BuildStatusRecord:
    id: str
    provider: BuildProvider
    status: str
    commit_hash: str
    branch: Optional[str] = None
    build_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    author: Optional[str] = None
    coverage: Optional[float] = None
    duration_seconds: Optional[float] = None
    web_url: Optional[str] = None
    stack_trace: Optional[str] = None
    failed_files: list[str] = field(default_factory=list)
    failed_nodes: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CICDIntegrator:
    """Normalizes CI/CD webhook payloads into a single build status shape."""

    def normalize(
        self,
        provider: BuildProvider,
        payload: dict[str, Any],
    ) -> BuildStatusRecord:
        if provider == "github_actions":
            return self._from_github_actions(payload)
        if provider == "gitlab_ci":
            return self._from_gitlab(payload)
        if provider == "jenkins":
            return self._from_jenkins(payload)
        raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def detect_provider(headers: dict[str, str], payload: dict[str, Any]) -> Optional[BuildProvider]:
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        if "x-github-event" in normalized_headers:
            return "github_actions"
        if "x-gitlab-event" in normalized_headers:
            return "gitlab_ci"
        if "x-jenkins" in normalized_headers:
            return "jenkins"

        if "workflow_run" in payload or "check_run" in payload:
            return "github_actions"
        if "object_kind" in payload and payload.get("object_kind") in {"pipeline", "build"}:
            return "gitlab_ci"
        if "build" in payload or payload.get("jenkins_url"):
            return "jenkins"
        return None

    def _from_github_actions(self, payload: dict[str, Any]) -> BuildStatusRecord:
        workflow_run = payload.get("workflow_run") or {}
        check_run = payload.get("check_run") or {}
        status_raw = workflow_run.get("conclusion") or check_run.get("conclusion") or workflow_run.get("status") or "unknown"
        status = self._normalize_status(status_raw)
        commit_hash = workflow_run.get("head_sha") or check_run.get("head_sha") or payload.get("after") or "unknown"

        failed_files = self._extract_failed_files(payload)
        return BuildStatusRecord(
            id=str(uuid.uuid4()),
            provider="github_actions",
            status=status,
            commit_hash=commit_hash,
            branch=workflow_run.get("head_branch"),
            build_id=str(workflow_run.get("id") or check_run.get("id") or ""),
            pipeline_id=str(workflow_run.get("run_number") or ""),
            author=(workflow_run.get("actor") or {}).get("login"),
            duration_seconds=self._duration_seconds(
                workflow_run.get("run_started_at"),
                workflow_run.get("updated_at"),
            ),
            web_url=workflow_run.get("html_url") or check_run.get("html_url"),
            stack_trace=self._extract_stack_trace(payload),
            failed_files=failed_files,
            failed_nodes=self._infer_failed_nodes(failed_files),
            raw_payload=payload,
        )

    def _from_gitlab(self, payload: dict[str, Any]) -> BuildStatusRecord:
        attrs = payload.get("object_attributes") or {}
        status_raw = attrs.get("status") or payload.get("build_status") or "unknown"
        status = self._normalize_status(status_raw)
        commit_hash = attrs.get("sha") or payload.get("checkout_sha") or "unknown"
        failed_files = self._extract_failed_files(payload)

        return BuildStatusRecord(
            id=str(uuid.uuid4()),
            provider="gitlab_ci",
            status=status,
            commit_hash=commit_hash,
            branch=attrs.get("ref"),
            build_id=str(attrs.get("id") or payload.get("build_id") or ""),
            pipeline_id=str(attrs.get("pipeline_id") or payload.get("pipeline_id") or ""),
            author=(payload.get("user") or {}).get("name"),
            coverage=self._as_float(attrs.get("coverage") or payload.get("coverage")),
            duration_seconds=self._as_float(attrs.get("duration")),
            web_url=attrs.get("url"),
            stack_trace=self._extract_stack_trace(payload),
            failed_files=failed_files,
            failed_nodes=self._infer_failed_nodes(failed_files),
            raw_payload=payload,
        )

    def _from_jenkins(self, payload: dict[str, Any]) -> BuildStatusRecord:
        build = payload.get("build") or {}
        status_raw = build.get("status") or build.get("result") or payload.get("status") or "unknown"
        status = self._normalize_status(status_raw)
        commit_hash = (
            payload.get("commit")
            or ((payload.get("scm") or {}).get("commit"))
            or "unknown"
        )
        failed_files = self._extract_failed_files(payload)

        return BuildStatusRecord(
            id=str(uuid.uuid4()),
            provider="jenkins",
            status=status,
            commit_hash=commit_hash,
            branch=(payload.get("scm") or {}).get("branch"),
            build_id=str(build.get("number") or payload.get("build_number") or ""),
            pipeline_id=str(payload.get("job_name") or ""),
            author=payload.get("user"),
            duration_seconds=self._as_float(build.get("duration")),
            web_url=build.get("full_url") or payload.get("jenkins_url"),
            stack_trace=self._extract_stack_trace(payload),
            failed_files=failed_files,
            failed_nodes=self._infer_failed_nodes(failed_files),
            raw_payload=payload,
        )

    @staticmethod
    def _normalize_status(status_raw: str) -> str:
        s = str(status_raw or "").lower()
        if s in {"success", "passed", "succeeded"}:
            return "success"
        if s in {"failure", "failed", "errored", "error"}:
            return "failed"
        if s in {"cancelled", "canceled"}:
            return "cancelled"
        if s in {"running", "in_progress", "pending"}:
            return "running"
        return "unknown"

    @staticmethod
    def _extract_failed_files(payload: dict[str, Any]) -> list[str]:
        text = json.dumps(payload, ensure_ascii=False)
        candidates = re.findall(r'([\w./-]+\.(?:py|ts|tsx|js|jsx|java|sql|cs|go|rb|php|kt))', text, flags=re.IGNORECASE)
        cleaned = []
        seen = set()
        for path in candidates:
            normalized = path.replace("\\", "/").strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned[:100]

    @staticmethod
    def _extract_stack_trace(payload: dict[str, Any]) -> Optional[str]:
        text = json.dumps(payload, ensure_ascii=False)
        trace_markers = ["Traceback", "Exception", "at ", "Caused by", "ERROR:"]
        if not any(marker in text for marker in trace_markers):
            return None
        return text[:5000]

    @staticmethod
    def _infer_failed_nodes(failed_files: list[str]) -> list[str]:
        # The graph nodes are namespace-based; file paths are enough to map nodes server-side.
        return [f"file:{item}" for item in failed_files[:100]]

    @staticmethod
    def _duration_seconds(start_raw: Any, end_raw: Any) -> Optional[float]:
        # GitHub sends ISO timestamps; keep this lightweight and optional.
        if not start_raw or not end_raw:
            return None
        return None

    @staticmethod
    def _as_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
