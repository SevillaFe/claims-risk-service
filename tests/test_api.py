from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_low_risk_claim():
    payload = {
        "claim_amount": 800,
        "policy_age_months": 36,
        "customer_age": 40,
        "prior_claims_count": 0,
        "suspicious_keywords_count": 0,
        "fraud_history": False,
    }
    response = client.post("/risk/score", json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body["risk_level"] == "low"
    assert body["risk_score"] == 0.0
    assert body["reasons"] == []


def test_high_risk_claim():
    payload = {
        "claim_amount": 15000,
        "policy_age_months": 2,
        "customer_age": 29,
        "prior_claims_count": 4,
        "suspicious_keywords_count": 4,
        "fraud_history": True,
    }
    response = client.post("/risk/score", json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body["risk_level"] == "high"
    assert body["risk_score"] == 100.0
    assert "high_claim_amount" in body["reasons"]
    assert "new_policy" in body["reasons"]
    assert "high_prior_claim_frequency" in body["reasons"]
    assert "suspicious_claim_text_patterns" in body["reasons"]
    assert "known_fraud_history" in body["reasons"]
