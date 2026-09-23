# claims-risk-service

End-to-end AI microservice focused on insurance claim risk scoring.

## Features

- Insurance-focused claim risk scoring endpoint
- Explainable output with risk level and contributing reasons
- Health endpoint for operational checks
- Test coverage for key API behavior

## API

### `GET /health`

Returns service status.

### `POST /risk/score`

Scores an insurance claim using a lightweight AI-inspired risk model.

Example request:

```json
{
  "claim_amount": 15000,
  "policy_age_months": 2,
  "customer_age": 29,
  "prior_claims_count": 4,
  "suspicious_keywords_count": 4,
  "fraud_history": true
}
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

```bash
pytest -q
```