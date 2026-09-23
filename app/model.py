"""Carga del modelo e inferencia. Separado de la API para poder testearlo aislado."""
import sys
import os
from pathlib import Path

import joblib
import numpy as np

# Configuración vía variables de entorno (12-factor app): en Kubernetes
# se inyectan desde un ConfigMap sin reconstruir la imagen.
MODEL_PATH = Path(os.getenv("MODEL_PATH", Path(__file__).parent / "model.joblib"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "0.1.0")

FEATURES = ["claim_amount", "policy_age_years", "prior_claims", "days_to_report"]


def load_model(path: Path = MODEL_PATH):
    return joblib.load(path)


def predict_risk(model, features: dict) -> float:
    """Devuelve la probabilidad (0-1) de que el siniestro sea de alto riesgo."""
    X = np.array([[features[name] for name in FEATURES]])
    return float(model.predict_proba(X)[0, 1])
