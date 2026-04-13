"""
Prediction Engine — lightweight ML driver for risk prediction.

Provides:
  - Feature extraction for namespace keys
  - Random forest risk predictor with scaler persistence
  - Fragility spotlight collection for the frontend
  - Commit learning log for incremental improvements
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from joblib import dump, load
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

from monitoring import record_prediction_request
from ollama_client import get_embedding

logger = logging.getLogger("insightgraph.prediction_engine")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_FILE = MODELS_DIR / "risk_predictor.pkl"
HISTORY_FILE = Path(__file__).resolve().parent / "data" / "commit_history.json"


class FeatureExtractor:
    FEATURE_NAMES = [
        "file_depth",
        "has_test",
        "change_size",
        "change_type_weight",
        "hotspot_hint",
        "change_frequency",
        "cyclomatic_complexity",
        "fan_in",
        "fan_out",
        "bug_history_count",
        "semantic_emb_mean",
        "semantic_emb_std",
        "semantic_emb_max",
        "semantic_emb_min",
    ]

    _change_weights: dict[str, float] = {
        "rename_parameter": 0.95,
        "change_column_type": 0.9,
        "change_method_signature": 0.85,
        "change_procedure_param": 0.8,
        "code_change": 0.75,
    }

    def __init__(self):
        self._embedding_cache: Dict[str, List[float]] = {}

    def extract(self, namespace_key: str, change_type: Optional[str], metadata: Optional[Dict[str, Any]] = None) -> List[float]:
        metadata = metadata or {}
        parts = [p for p in namespace_key.replace("::", ":").replace(".", ":").split(":") if p]
        file_depth = len(parts)
        has_test = any("test" in p.lower() for p in parts)
        change_size = float(metadata.get("change_count") or len(metadata.get("changed_files") or []) or 1)
        change_type_weight = float(self._change_weights.get(change_type or "code_change", 0.7))
        hotspot_hint = float(metadata.get("hotspot_score") or 0)
        change_frequency = float(metadata.get("change_frequency") or metadata.get("frequency") or 1)
        cyclomatic_complexity = float(metadata.get("cyclomatic_complexity") or 1)
        fan_in = float(metadata.get("fan_in") or 0)
        fan_out = float(metadata.get("fan_out") or 0)
        bug_history_count = float(metadata.get("bug_history_count") or 0)
        semantic_features = self._extract_semantic_features(namespace_key, metadata)
        return [
            float(file_depth),
            float(has_test),
            change_size,
            change_type_weight,
            hotspot_hint,
            change_frequency,
            cyclomatic_complexity,
            fan_in,
            fan_out,
            bug_history_count,
            *semantic_features,
        ]

    def extract_dict(self, namespace_key: str, change_type: Optional[str], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        values = self.extract(namespace_key, change_type, metadata)
        return dict(zip(self.FEATURE_NAMES, values))

    def _extract_semantic_features(self, namespace_key: str, metadata: Dict[str, Any]) -> List[float]:
        semantic_text = metadata.get("semantic_text")
        if not semantic_text:
            changed_files = metadata.get("changed_files") or []
            semantic_text = " ".join([namespace_key, *changed_files])

        cache_key = str(semantic_text)[:512]
        embedding = self._embedding_cache.get(cache_key)
        if embedding is None and not metadata.get("disable_semantic_embedding"):
            embedding = get_embedding(cache_key)
            if embedding:
                self._embedding_cache[cache_key] = embedding
        if not embedding:
            # Deterministic fallback keeps model dimensions stable even without Ollama.
            digest = hashlib.sha256(cache_key.encode("utf-8")).digest()
            embedding = [b / 255.0 for b in digest[:16]]

        vector = np.array(embedding, dtype=np.float32)
        return [
            float(np.mean(vector)),
            float(np.std(vector)),
            float(np.max(vector)),
            float(np.min(vector)),
        ]


@dataclass
class PredictionRecord:
    node_key: str
    predicted_risk: float
    features: Dict[str, float]
    timestamp: float
    metadata: Dict[str, Any]


class PredictionEngine:
    def __init__(self, model_path: Path = MODEL_FILE):
        self.model_path = Path(model_path)
        self.model: Optional[RandomForestRegressor] = None
        self.scaler: Optional[StandardScaler] = None
        self._extractor = FeatureExtractor()
        self._recent_predictions: Dict[str, PredictionRecord] = {}
        self._history_lock = asyncio.Lock()
        self._ensure_paths()
        self._load_model()

    def _ensure_paths(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not HISTORY_FILE.exists():
            HISTORY_FILE.write_text("[]")

    def _load_model(self) -> None:
        if not self.model_path.exists():
            logger.warning("Prediction model not found at %s, falling back to heuristics", self.model_path)
            return
        try:
            data = load(self.model_path)
            self.model = data.get("model")
            self.scaler = data.get("scaler")
            logger.info("Loaded prediction model from %s", self.model_path)
        except Exception as exc:
            logger.warning("Failed to load prediction model: %s", exc)
            self.model = None
            self.scaler = None

    def predict_risk_score(
        self,
        node_key: str,
        change_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        features = self._extractor.extract(node_key, change_type, metadata)
        prediction = self._compute_score(features)
        pred = max(0.0, min(100.0, prediction))
        record_prediction_request()
        self._recent_predictions[node_key] = PredictionRecord(
            node_key=node_key,
            predicted_risk=pred,
            features=self._extractor.extract_dict(node_key, change_type, metadata),
            timestamp=time.time(),
            metadata=metadata or {},
        )
        return pred

    def _compute_score(self, features: List[float]) -> float:
        if self.model and self.scaler:
            try:
                scaled = self.scaler.transform([features])
                return float(self.model.predict(scaled)[0])
            except Exception as exc:
                logger.debug("Prediction failed, falling back to heuristic: %s", exc)
        return self._heuristic_score(features)

    def _heuristic_score(self, features: List[float]) -> float:
        # file_depth, has_test, change_size, change_type_weight, hotspot_hint, change_frequency, cyclomatic_complexity, fan_in, fan_out, bug_history_count
        base_score = sum(features[:3]) * 3 + features[3] * 20 + features[4] * 1.5 + features[5] * 2
        complexity_score = features[6] * 0.5  # cyclomatic_complexity
        coupling_score = (features[7] + features[8]) * 1.0  # fan_in + fan_out
        bug_score = features[9] * 5.0  # bug_history_count
        score = base_score + complexity_score + coupling_score + bug_score
        noise = random.uniform(-5, 5)
        return score + noise

    def identify_fragility_points(self, limit: int = 20) -> List[Dict[str, Any]]:
        sorted_predictions = sorted(
            self._recent_predictions.values(),
            key=lambda record: record.predicted_risk,
            reverse=True,
        )
        return [
            {
                "node_key": record.node_key,
                "predicted_risk": record.predicted_risk,
                "features": record.features,
                "metadata": record.metadata,
                "timestamp": record.timestamp,
            }
            for record in sorted_predictions[:limit]
        ]

    async def learn_from_commit(self, commit_hash: str, success: bool, metadata: Optional[Dict[str, Any]] = None) -> None:
        metadata = metadata or {}
        target_key = metadata.get("target_key", "unknown")
        change_type = metadata.get("change_type", "code_change")
        features = self._extractor.extract_dict(target_key, change_type, metadata)
        entry = {
            "commit_hash": commit_hash,
            "success": success,
            "change_type": change_type,
            "target_key": target_key,
            "features": features,
            "label": metadata.get("label", 30.0 if success else 70.0),
            "timestamp": time.time(),
        }
        async with self._history_lock:
            history = await self._read_history()
            history.append(entry)
            await self._write_history(history)

    async def _read_history(self) -> List[Dict[str, Any]]:
        def _inner() -> List[Dict[str, Any]]:
            try:
                return json.loads(HISTORY_FILE.read_text())
            except Exception:
                return []
        return await asyncio.to_thread(_inner)

    async def _write_history(self, history: List[Dict[str, Any]]) -> None:
        def _inner() -> None:
            HISTORY_FILE.write_text(json.dumps(history, indent=2))
        await asyncio.to_thread(_inner)
