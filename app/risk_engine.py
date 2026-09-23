from app.schemas import ClaimInput, RiskResponse


def _risk_level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def score_claim(claim: ClaimInput) -> RiskResponse:
    score = 0.0
    reasons: list[str] = []

    if claim.claim_amount > 10000:
        score += 20
        reasons.append("high_claim_amount")
    elif claim.claim_amount > 5000:
        score += 10
        reasons.append("moderate_claim_amount")

    if claim.policy_age_months < 6:
        score += 20
        reasons.append("new_policy")
    elif claim.policy_age_months < 12:
        score += 10
        reasons.append("young_policy")

    if claim.prior_claims_count >= 3:
        score += 20
        reasons.append("high_prior_claim_frequency")
    elif claim.prior_claims_count == 2:
        score += 10
        reasons.append("moderate_prior_claim_frequency")

    if claim.suspicious_keywords_count > 0:
        keyword_weight = min(20, claim.suspicious_keywords_count * 5)
        score += keyword_weight
        reasons.append("suspicious_claim_text_patterns")

    if claim.fraud_history:
        score += 20
        reasons.append("known_fraud_history")

    normalized = max(0.0, min(100.0, round(score, 2)))
    return RiskResponse(
        risk_score=normalized, risk_level=_risk_level(normalized), reasons=reasons
    )
