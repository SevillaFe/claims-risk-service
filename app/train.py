"""Entrena un modelo de riesgo de siniestros con datos SINTÉTICOS.

Se ejecuta durante el build de Docker (el binario del modelo NO va a git):
    python -m app.train
En producción el modelo vendría de un registry (S3 / SageMaker Model Registry)
y tendría su propio pipeline de entrenamiento.
"""

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.model import FEATURES, MODEL_PATH


def make_synthetic_claims(n: int = 5000, seed: int = 42):
    """Genera siniestros ficticios con una relación de riesgo plausible."""
    rng = np.random.default_rng(seed)
    claim_amount = rng.lognormal(mean=8, sigma=1, size=n)  # importe EUR (mediana ~3.000)
    policy_age_years = rng.uniform(0, 20, n)  # antigüedad de la póliza
    prior_claims = rng.poisson(0.5, n)  # siniestros previos
    days_to_report = rng.exponential(7, n)  # días hasta comunicar el siniestro

    # "Verdad" oculta: más importe, más siniestros previos y más retraso => más riesgo
    logit = (
        -2.5
        + 0.8 * np.log(claim_amount / 3000)
        - 0.15 * policy_age_years
        + 0.9 * prior_claims
        + 0.05 * days_to_report
    )
    y = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    X = np.column_stack([claim_amount, policy_age_years, prior_claims, days_to_report])
    return X, y


def main() -> None:
    X, y = make_synthetic_claims()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression())])
    model.fit(X_train, y_train)

    auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    print(f"Features: {FEATURES} | Test AUC: {auc:.3f}")

    joblib.dump(model, MODEL_PATH)
    print(f"Modelo guardado en {MODEL_PATH}")


if __name__ == "__main__":
    main()
