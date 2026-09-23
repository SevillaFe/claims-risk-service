VALID_CLAIM = {
    "claim_amount": 4500.0,
    "policy_age_years": 3.0,
    "prior_claims": 1,
    "days_to_report": 12.0,
}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_predict_valid_claim(client):
    r = client.post("/predict", json=VALID_CLAIM)
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["risk_class"] in {"high", "low"}


def test_predict_rejects_negative_amount(client):
    r = client.post("/predict", json={**VALID_CLAIM, "claim_amount": -10})
    assert r.status_code == 422  # validación de Pydantic


def test_riskier_claim_scores_higher(client):
    """Test de comportamiento del modelo, no solo de la API."""
    safe = {**VALID_CLAIM, "prior_claims": 0, "days_to_report": 1, "policy_age_years": 15}
    risky = {**VALID_CLAIM, "prior_claims": 4, "days_to_report": 60, "policy_age_years": 0}
    s = client.post("/predict", json=safe).json()["risk_score"]
    r = client.post("/predict", json=risky).json()["risk_score"]
    assert r > s


def test_metrics_exposed(client):
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text
