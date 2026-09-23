from fastapi import FastAPI

from app.risk_engine import score_claim
from app.schemas import ClaimInput, RiskResponse

app = FastAPI(
    title="Claims Risk Service",
    description="AI microservice for insurance claim risk scoring",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/risk/score", response_model=RiskResponse)
def risk_score(payload: ClaimInput) -> RiskResponse:
    return score_claim(payload)
