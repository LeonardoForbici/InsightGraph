"""Simple client that fetches semantic embeddings from Ollama."""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger("insightgraph.ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "0.35"))
OLLAMA_CACHE_LIMIT = int(os.environ.get("OLLAMA_CACHE_LIMIT", "128"))
_API_EMBEDDINGS_ENDPOINT = f"{OLLAMA_URL}/api/embeddings"
_EMBED_ENDPOINT = f"{OLLAMA_URL}/embed"


def get_embedding(text: str) -> Optional[List[float]]:
    """Return the embedding for the provided text, or None on failure."""
    if not text:
        return None

    payload_api = {
        "model": OLLAMA_MODEL,
        "prompt": text,
    }
    payload_embed = {
        "model": OLLAMA_MODEL,
        "text": text,
    }

    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            response = client.post(_API_EMBEDDINGS_ENDPOINT, json=payload_api)
            if response.status_code != 200:
                response = client.post(_EMBED_ENDPOINT, json=payload_embed)
        if response.status_code != 200:
            logger.debug(
                "Ollama embedding failed [%s]: %s",
                response.status_code,
                response.text[:160],
            )
            return None
        data = response.json()
        embedding = data.get("embedding") or data.get("embeddings") or data.get("vector")
        if isinstance(embedding, list) and embedding:
            return [float(v) for v in embedding]
    except httpx.HTTPError as err:
        logger.debug("Ollama request error: %s", err)
    except ValueError as err:  # invalid JSON
        logger.debug("Ollama returned invalid JSON: %s", err)
    except Exception as err:  # pragma: no cover
        logger.debug("Unexpected error fetching Ollama embedding: %s", err)
    return None
