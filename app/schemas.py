from pydantic import BaseModel, Field


class ClaimInput(BaseModel):
    claim_amount: float = Field(gt=0)
    policy_age_months: int = Field(ge=0)
    customer_age: int = Field(ge=18)
    prior_claims_count: int = Field(ge=0)
    suspicious_keywords_count: int = Field(ge=0)
    fraud_history: bool = False


class RiskResponse(BaseModel):
    risk_score: float
    risk_level: str
    reasons: list[str]
