"""API del servicio. Tres ideas de operación en un solo fichero:
1. Liveness vs. readiness  (/health, /ready)  -> lo usan las probes de Kubernetes
2. Métricas Prometheus     (/metrics)         -> monitoring
3. Logs JSON estructurados                    -> consultables en CloudWatch / Loki
"""

import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from app.model import MODEL_VERSION, load_model, predict_risk


# ---------- Logging estructurado ----------
class JsonFormatter(logging.Formatter):
    """Una línea JSON por evento: fácil de filtrar (p. ej. status >= 500) en un log backend."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


handler = logging.StreamHandler()  # stdout: en contenedores NO se escribe a ficheros
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
logger = logging.getLogger("claims-risk-service")


# ---------- Métricas ----------
REQUESTS = Counter("http_requests_total", "Peticiones HTTP", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Latencia HTTP", ["path"])
PREDICTIONS = Counter("predictions_total", "Predicciones por clase de riesgo", ["risk_class"])


# ---------- Ciclo de vida: cargar el modelo UNA vez al arrancar ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = None
    try:
        app.state.model = load_model()
        logger.info("model loaded", extra={"extra_fields": {"model_version": MODEL_VERSION}})
    except Exception:
        # No tiramos el proceso: /ready devolverá 503 y Kubernetes no le enviará tráfico
        logger.exception("model could not be loaded")
    yield


app = FastAPI(title="Claims Risk Service", version=MODEL_VERSION, lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    path = request.url.path
    if path != "/metrics":  # no medimos el propio scraping de Prometheus
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(path).observe(duration)
        logger.info(
            "request",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                }
            },
        )
    return response


# ---------- Esquemas: validación de entrada con Pydantic ----------
class ClaimRequest(BaseModel):
    claim_amount: float = Field(gt=0, description="Importe del siniestro en EUR")
    policy_age_years: float = Field(ge=0, le=100)
    prior_claims: int = Field(ge=0, le=50)
    days_to_report: float = Field(ge=0, le=3650)


class RiskResponse(BaseModel):
    risk_score: float
    risk_class: str
    model_version: str


# ---------- Endpoints ----------
@app.get("/health")
def health():
    """Liveness: ¿el proceso está vivo? Si falla, Kubernetes REINICIA el pod."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: ¿puede atender tráfico? Si falla, Kubernetes le QUITA tráfico (no reinicia)."""
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    return {"status": "ready", "model_version": MODEL_VERSION}


@app.post("/predict", response_model=RiskResponse)
def predict(claim: ClaimRequest):
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    score = predict_risk(app.state.model, claim.model_dump())
    risk_class = "high" if score >= 0.5 else "low"
    PREDICTIONS.labels(risk_class).inc()
    return RiskResponse(
        risk_score=round(score, 4), risk_class=risk_class, model_version=MODEL_VERSION
    )


@app.get("/metrics")
def metrics():
    """Endpoint que Prometheus consulta ("scrapea") periódicamente."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
