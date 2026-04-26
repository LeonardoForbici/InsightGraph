from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class OllamaModelConfig:
    fast: str
    chat: str
    complex: str
    embed: str
    small: str


class OllamaServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        model: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.model = model
        self.status_code = status_code


class OllamaRuntime:
    def __init__(
        self,
        *,
        base_url: str,
        models: OllamaModelConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.models = models
        self.logger = logger or logging.getLogger("insightgraph.ollama")

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        timeout: float,
        retries: int = 1,
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if options:
            payload["options"] = options
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return await self._post_json(
            path="/api/generate",
            payload=payload,
            timeout=timeout,
            retries=retries,
            operation="generate",
            model=model,
        )

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        timeout: float,
        retries: int = 1,
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
        fallback_generate_prompt: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if options:
            payload["options"] = options
        if keep_alive:
            payload["keep_alive"] = keep_alive
        try:
            return await self._post_json(
                path="/api/chat",
                payload=payload,
                timeout=timeout,
                retries=retries,
                operation="chat",
                model=model,
            )
        except OllamaServiceError as exc:
            if exc.status_code != 404 or not fallback_generate_prompt:
                raise
            self.logger.warning("Ollama /api/chat unavailable; falling back to /api/generate")
            return await self.generate(
                model=model,
                prompt=fallback_generate_prompt,
                timeout=timeout,
                retries=retries,
                options=options,
                keep_alive=keep_alive,
            )

    async def embeddings(
        self,
        *,
        model: str,
        text: str,
        timeout: float = 8.0,
        retries: int = 1,
    ) -> list[float]:
        payload = {"model": model, "prompt": text}
        data = await self._post_json(
            path="/api/embeddings",
            payload=payload,
            timeout=timeout,
            retries=retries,
            operation="embeddings",
            model=model,
        )
        embedding = data.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise OllamaServiceError(
                "Empty embedding response from Ollama",
                operation="embeddings",
                model=model,
            )
        return [float(x) for x in embedding]

    def embeddings_sync(
        self,
        *,
        model: str,
        text: str,
        timeout: float = 8.0,
    ) -> list[float]:
        payload = {"model": model, "prompt": text}
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{self.base_url}/api/embeddings", json=payload)
                resp.raise_for_status()
                data = resp.json()
            embedding = data.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise OllamaServiceError(
                    "Empty embedding response from Ollama",
                    operation="embeddings_sync",
                    model=model,
                )
            return [float(x) for x in embedding]
        except Exception as exc:  # pragma: no cover - best effort in sync contexts
            raise self._map_error(exc, operation="embeddings_sync", model=model)

    async def _post_json(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        timeout: float,
        retries: int,
        operation: str,
        model: str | None,
    ) -> dict[str, Any]:
        attempts = max(1, retries + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{self.base_url}{path}", json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except Exception as exc:
                mapped = self._map_error(exc, operation=operation, model=model)
                last_error = mapped
                retriable = isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError))
                if isinstance(exc, httpx.HTTPStatusError):
                    status_code = exc.response.status_code
                    retriable = status_code >= 500 or status_code == 429
                if attempt < attempts and retriable:
                    await asyncio.sleep(0.25 * attempt)
                    continue
                raise mapped
        if isinstance(last_error, OllamaServiceError):
            raise last_error
        raise OllamaServiceError(
            "Unknown Ollama failure",
            operation=operation,
            model=model,
        )

    def _map_error(self, exc: Exception, *, operation: str, model: str | None) -> OllamaServiceError:
        if isinstance(exc, OllamaServiceError):
            return exc
        if isinstance(exc, httpx.ConnectError):
            return OllamaServiceError(
                "Nao foi possivel conectar ao Ollama local. Verifique se o servico esta em execucao.",
                operation=operation,
                model=model,
            )
        if isinstance(exc, httpx.ReadTimeout):
            return OllamaServiceError(
                f"Ollama excedeu tempo limite na operacao '{operation}' com o modelo '{model or 'unknown'}'.",
                operation=operation,
                model=model,
            )
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            detail = ""
            try:
                payload = exc.response.json()
                detail = payload.get("error") or json.dumps(payload)
            except Exception:
                detail = exc.response.text[:200]
            return OllamaServiceError(
                f"Ollama retornou HTTP {status} na operacao '{operation}'. {detail}".strip(),
                operation=operation,
                model=model,
                status_code=status,
            )
        return OllamaServiceError(
            f"Falha inesperada em Ollama ({operation}): {exc}",
            operation=operation,
            model=model,
        )
