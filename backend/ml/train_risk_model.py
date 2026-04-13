"""
Training script for the Prediction Engine.

Generates a dataset (with synthetic fallback), trains a RandomForestRegressor,
and persists the model + scaler under backend/models/risk_predictor.pkl.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from joblib import dump
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

from prediction_engine import FeatureExtractor

MODEL_FILE = Path(__file__).resolve().parent.parent / "models" / "risk_predictor.pkl"
HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "commit_history.json"


def load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text())
    except Exception:
        return []


def synthetic_history(entries: int = 200) -> list[dict]:
    extractor = FeatureExtractor()
    history = []
    for i in range(entries):
        target = f"module{random.randint(1,50)}:Class{random.randint(1,20)}"
        change_type = random.choice(["rename_parameter", "change_column_type", "change_method_signature"])
        metadata = {
            "change_count": random.randint(1, 12),
            "hotspot_score": random.uniform(0, 25),
            "change_frequency": random.uniform(0.1, 5.0),
            "disable_semantic_embedding": True,
        }
        features = extractor.extract_dict(target, change_type, metadata)
        label = min(100.0, max(0.0, random.gauss(60 if metadata["hotspot_score"] > 15 else 30, 15)))
        history.append({
            "commit_hash": f"fake-{i}-{random.randint(1000,9999)}",
            "success": label < 60,
            "target_key": target,
            "change_type": change_type,
            "features": features,
            "label": label,
            "timestamp": 0,
        })
    return history


def build_dataset(history: list[dict]) -> tuple[list[list[float]], list[float]]:
    extractor = FeatureExtractor()
    X: list[list[float]] = []
    y: list[float] = []
    for entry in history:
        target = entry.get("target_key", "moduleX")
        change_type = entry.get("change_type", "code_change")
        metadata = entry.get("metadata") or {}
        features = entry.get("features")
        if not features:
            features = extractor.extract_dict(target, change_type, metadata)
        X.append([float(features[name]) for name in extractor.FEATURE_NAMES])
        y.append(float(entry.get("label", 50.0)))
    if not X:
        synth = synthetic_history(150)
        return build_dataset(synth)
    return X, y


def train() -> None:
    history = load_history()
    if not history:
        history = synthetic_history()
    X, y = build_dataset(history)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = RandomForestRegressor(n_estimators=80, max_depth=12, random_state=42)
    model.fit(X_scaled, y)
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    dump({"model": model, "scaler": scaler}, MODEL_FILE)
    print(f"Trained risk model with {len(X)} samples and saved to {MODEL_FILE}")


if __name__ == "__main__":
    train()
