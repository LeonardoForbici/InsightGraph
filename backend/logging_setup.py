"""Structured logging helpers with correlation id support."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get("-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    mode = os.getenv("LOG_FORMAT", "json").lower()
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        if mode == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            if mode == "json":
                handler.setFormatter(JsonFormatter())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        corr_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        token = correlation_id_ctx.set(corr_id)
        try:
            response = await call_next(request)
            response.headers["x-correlation-id"] = corr_id
            return response
        finally:
            correlation_id_ctx.reset(token)
