# claims-risk-service — Complete Build Guide

A step-by-step guide to rebuild this project **from an empty folder**: a small AI inference service taken through the full operational lifecycle — Python API, Docker, GitLab CI, Terraform on AWS and Kubernetes.

Every phase follows the same structure:

1. **Concepts** — what the tool is and why it exists.
2. **Files** — the full code, explained block by block.
3. **Practice** — commands to run, things to break on purpose, and what to observe.
4. **Troubleshooting** — real problems met while building this, and how they were solved.
5. **Interview notes** — the questions this phase typically raises, with short answers.

> The goal of the project is **operations, not modelling**. The model is deliberately simple (a logistic regression on synthetic data). What matters is everything around it: health checks, metrics, logs, containers, pipelines, infrastructure and orchestration.

---

## Table of contents

1. [What you will build](#1-what-you-will-build)
2. [The guiding principles](#2-the-guiding-principles)
3. [Prerequisites and tool installation (macOS)](#3-prerequisites-and-tool-installation-macos)
4. [Phase 1 — The Python application](#4-phase-1--the-python-application)
5. [Phase 2 — Docker](#5-phase-2--docker)
6. [Phase 3 — GitLab CI](#6-phase-3--gitlab-ci)
7. [Phase 4 — Terraform on AWS](#7-phase-4--terraform-on-aws)
8. [Phase 5 — Kubernetes with kind](#8-phase-5--kubernetes-with-kind)
9. [The end-to-end flow](#9-the-end-to-end-flow)
10. [Interview cheat sheet](#10-interview-cheat-sheet)
11. [Command cheat sheet](#11-command-cheat-sheet)
12. [Next steps](#12-next-steps)

---

## 1. What you will build

A microservice that scores the risk of an insurance claim, operated like a production AI service.

```
 git push ──► GitLab CI: lint ─► test ─► build ──► GitLab Registry / AWS ECR (via OIDC)
                                   └──► terraform validate
                                             │
 Terraform ──► AWS: ECR · S3 (model artefacts) · IAM role with OIDC (least privilege)
                                             │
 Kubernetes (kind) ◄── image ── Deployment (2 replicas, probes, limits) ─► Service
                                   └── /metrics (Prometheus) · JSON logs (stdout)
```

| Component | What it is | Operational concern it covers |
|---|---|---|
| **App** | FastAPI + scikit-learn model; `/health`, `/ready`, `/predict`, `/metrics` | Putting an AI service into operation |
| **Docker** | Multi-stage Dockerfile, non-root user, slim image | Container technologies |
| **Observability** | Structured JSON logs, Prometheus metrics (requests, latency, predictions) | Monitoring & observability |
| **GitLab CI** | `lint → test → build → push`, plus Terraform validation | CI/CD |
| **Terraform** | ECR, S3 and an IAM role trusted via OIDC (no access keys) | Infrastructure as Code, permissions, security, costs |
| **Kubernetes** | Deployment with liveness/readiness probes, resource limits, ConfigMap, Service | Orchestration |

Final repository layout:

```
claims-risk-service/
├── app/
│   ├── __init__.py
│   ├── model.py          # the "contract": features, model path, inference
│   ├── train.py          # synthetic data + training
│   └── main.py           # FastAPI app: endpoints, logging, metrics
├── tests/
│   ├── __init__.py
│   ├── conftest.py       # pytest fixture: trains + loads the model once
│   └── test_api.py
├── k8s/
│   ├── configmap.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── infra/
│   ├── versions.tf
│   ├── backend.tf
│   ├── variables.tf
│   ├── main.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .gitlab-ci.yml
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
└── BUILD_GUIDE.md        # this file
```

---

## 2. The guiding principles

### 2.1 Build from the inside out

```
code → test it → package it (Docker) → infrastructure (Terraform)
     → run it (Kubernetes) → automate it (CI) → document it (README)
```

Each layer rests on the previous one. There is no point writing a CI pipeline before you know which test commands it must run. In practice CI is set up early (right after Docker) so that every later change is checked automatically — this guide follows that order.

### 2.2 Design from the requirements

Before writing code, ask: *what does the person who operates this service need?* Not just a prediction endpoint, but also:

- a way to know if the process is **alive** (`/health`),
- a way to know if it can **serve traffic** (`/ready`),
- **metrics** to build dashboards and alerts (`/metrics`),
- **logs** that machines can filter (JSON).

### 2.3 Convention + configuration

`python -m app.train` and `uvicorn app.main:app` are told exactly what to run. Most other tools work differently: they follow a **naming convention** to discover what to do, and read a **configuration file** to adjust it.

| Tool | Convention (what it looks for) | Configuration |
|---|---|---|
| ruff | All `*.py` files under the given path (skips `.venv`, `.git`, `.gitignore` entries) | `[tool.ruff]` in `pyproject.toml` |
| pytest | Files `test_*.py`, functions `test_*`, classes `Test*`; auto-loads `conftest.py` | `[tool.pytest.ini_options]` in `pyproject.toml` |
| Docker | A file named `Dockerfile` in the build context | `.dockerignore` |
| GitLab | A file named `.gitlab-ci.yml` at the repo root | The file itself |
| Terraform | **All** `*.tf` files in the folder, read as one | `terraform.tfvars`, `TF_VAR_*` |
| kubectl | `kubectl apply -f k8s/` applies every YAML in the folder | — |
| AWS CLI / Terraform AWS provider | Credentials in `~/.aws/credentials` or environment variables | `aws configure` |

Knowing **how each tool discovers what to do** is what lets you debug when something does not run.

### 2.4 Reproduce CI failures locally first

The pipeline runs the same commands you run by hand. When it fails, reproduce the failure on your machine **before** trying to fix it. If you cannot see the error locally, you are fixing blind.

---

## 3. Prerequisites and tool installation (macOS)

| Tool | Install | Verify |
|---|---|---|
| Python ≥ 3.11 | `brew install python@3.12` | `python3.12 --version` |
| Docker Desktop | Download from docker.com (pick **Apple Silicon** or **Intel** to match your chip) | `docker version` (must show *Client* **and** *Server*) |
| Git | Preinstalled with Xcode Command Line Tools | `git --version` |
| Terraform ≥ 1.6 | `brew tap hashicorp/tap && brew install hashicorp/tap/terraform` | `terraform version` |
| AWS CLI v2 | Official `.pkg` installer (see below) | `aws --version` |
| kind + kubectl | `brew install kind kubectl` | `kind version`, `kubectl version --client` |
| VS Code (optional) | code.visualstudio.com | — |

Accounts needed: **GitHub** (optional mirror), **GitLab.com** (CI), **a personal AWS account** (Terraform). Never use a corporate AWS account for experiments.

### Troubleshooting installation

**`zsh: command not found: python`** — macOS only ships `python3`. Inside an activated virtualenv, `python` and `pip` work because they point to the venv. Check the version: the pinned dependencies (numpy 2.4, scikit-learn 1.8) need **Python ≥ 3.11**; the macOS system Python (3.9) is too old.

**`zsh: command not found: docker`** after installing Docker Desktop — the CLI is added the first time you **open** Docker Desktop and complete its setup (accept the recommended settings; it may ask for your password). Then open a **new terminal tab** so the shell reloads its `PATH`. If it still fails:

```bash
ls ~/.docker/bin/docker        # "user" installation
ls /usr/local/bin/docker       # "system" installation
# If only the first exists:
echo 'export PATH="$HOME/.docker/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Or switch Docker Desktop to *Settings → Advanced → System (requires password)*.

**`brew install terraform` installs an old version** — Homebrew core stopped updating Terraform after HashiCorp's licence change. Always use the `hashicorp/tap` formula above.

**AWS CLI from Homebrew crashes** with `dlopen(... pyexpat ...) Symbol not found: _XML_SetAllocTrackerActivationThreshold` — Homebrew's `awscli` depends on Homebrew's Python, which can be incompatible with the system `libexpat`. Use the official installer, which bundles its own Python:

```bash
brew uninstall awscli
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
rm AWSCLIV2.pkg
# open a NEW terminal tab
which aws        # /usr/local/bin/aws
aws --version    # aws-cli/2.x
```

**Hidden files** — files starting with a dot (`.gitignore`, `.dockerignore`, `.gitlab-ci.yml`) are invisible in Finder. Use `ls -la` in the terminal, or press `Cmd + Shift + .` in Finder to toggle them.

---

## 4. Phase 1 — The Python application

### 4.1 Create the repository and the folder structure

Create an empty repository on GitHub (optional) and clone it, or just create a folder:

```bash
git clone https://github.com/YOUR_USER/claims-risk-service.git
cd claims-risk-service
mkdir app tests k8s infra
touch app/__init__.py tests/__init__.py
```

The empty `__init__.py` turns a folder into a **Python package**. That is what allows `from app.model import ...` and `python -m app.train`.

### 4.2 Create the virtual environment

```bash
python3.12 -m venv .venv          # or python3 -m venv .venv if python3 is >= 3.11
source .venv/bin/activate         # the prompt now starts with (.venv)
which python                      # .../claims-risk-service/.venv/bin/python
```

A virtualenv isolates the Python version and the project's libraries from the rest of the system. Docker takes the same idea further by isolating *everything*.

### 4.3 Dependencies: install first, pin later

The workflow used here: install the libraries **without versions** while developing, and once everything works, freeze the exact installed versions.

```bash
pip install fastapi uvicorn scikit-learn joblib numpy prometheus-client pydantic pytest httpx ruff
pip freeze | grep -iE "^(fastapi|uvicorn|scikit-learn|joblib|numpy|prometheus.client|pydantic|pytest|httpx|ruff)=="
```

Then split them into two files:

**`requirements.txt`** — what the app needs to **run** (goes into the Docker image):

```text
# Runtime dependencies (they go into the image). Pinned versions = reproducible builds.
fastapi==0.141.1
uvicorn==0.53.0
scikit-learn==1.8.0
joblib==1.5.3
numpy==2.4.4
prometheus-client==0.26.0
pydantic==2.13.5
```

**`requirements-dev.txt`** — what you need to **develop and test** (not shipped to production, keeping the image smaller and safer):

```text
# Development and CI only (NOT shipped in the production image)
pytest==9.1.1
httpx==0.28.1
ruff==0.16.8
```

Pinned versions make builds **reproducible**: the same code produces the same image today and in six months.

### 4.4 `app/model.py` — the "contract"

Written first because it defines what training and the API share: which features exist, where the model lives, and how to predict.

```python
"""Model loading and inference. Kept separate from the API so it can be tested in isolation."""

import os
from pathlib import Path

import joblib
import numpy as np

# Configuration via environment variables (12-factor app): in Kubernetes they are
# injected from a ConfigMap without rebuilding the image.
MODEL_PATH = Path(os.getenv("MODEL_PATH", Path(__file__).parent / "model.joblib"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "0.1.0")

FEATURES = ["claim_amount", "policy_age_years", "prior_claims", "days_to_report"]


def load_model(path: Path = MODEL_PATH):
    return joblib.load(path)


def predict_risk(model, features: dict) -> float:
    """Return the probability (0-1) that the claim is high risk."""
    X = np.array([[features[name] for name in FEATURES]])
    return float(model.predict_proba(X)[0, 1])
```

| Import | Purpose |
|---|---|
| `os` | Read environment variables (`MODEL_PATH`, `MODEL_VERSION`) — configure without touching code |
| `pathlib.Path` | Build file paths that work on any operating system |
| `joblib` | Save / load the trained model to / from disk |
| `numpy` | Turn the input dictionary into the matrix scikit-learn expects |

- `FEATURES` is an **ordered** list: the model receives a matrix, not named columns, so order matters.
- **Why separate from `main.py`?** Separation of concerns: the model logic can be tested and changed without touching the API.

### 4.5 `app/train.py` — synthetic data and training

```python
"""Train a claims-risk model on SYNTHETIC data.

Runs during the Docker build (the model binary is NOT committed to git):
    python -m app.train
In production the model would come from a registry (S3 / SageMaker Model Registry)
and have its own training pipeline.
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
    """Generate fictitious claims with a plausible risk relationship."""
    rng = np.random.default_rng(seed)
    claim_amount = rng.lognormal(mean=8, sigma=1, size=n)  # EUR amount (median ~3,000)
    policy_age_years = rng.uniform(0, 20, n)  # age of the policy
    prior_claims = rng.poisson(0.5, n)  # number of previous claims
    days_to_report = rng.exponential(7, n)  # days until the claim was reported

    # Hidden "truth": higher amount, more prior claims and longer delay => higher risk
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
    print(f"Model saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
```

| Import | Purpose |
|---|---|
| `numpy` | Random data with realistic distributions (lognormal for amounts, Poisson for counts, exponential for delays) |
| `train_test_split` | Split data 80 % train / 20 % test |
| `Pipeline` + `StandardScaler` + `LogisticRegression` | The model: scale, then classify |
| `roc_auc_score` | Measure model quality (AUC) |
| `joblib` | Save the trained model |
| `from app.model import FEATURES, MODEL_PATH` | Reuse the contract from 4.4 |

Flow of `main()`: generate 5,000 fictitious claims with a hidden risk rule → split → train the pipeline → print the AUC (≈ 0.84) → save `app/model.joblib`.

**Why a `Pipeline`?** The scaler travels *inside* the model. In production you cannot forget to scale the input — the pipeline does it.

### 4.6 `app/main.py` — the API, built in layers

```python
"""Service API. Three operational ideas in a single file:
1. Liveness vs. readiness  (/health, /ready)  -> used by Kubernetes probes
2. Prometheus metrics      (/metrics)         -> monitoring
3. Structured JSON logs                       -> queryable in CloudWatch / Loki
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


# ---------- Structured logging ----------
class JsonFormatter(logging.Formatter):
    """One JSON line per event: easy to filter (e.g. status >= 500) in a log backend."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


handler = logging.StreamHandler()  # stdout: containers do NOT write log files
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
logger = logging.getLogger("claims-risk-service")


# ---------- Metrics ----------
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP latency", ["path"])
PREDICTIONS = Counter("predictions_total", "Predictions by risk class", ["risk_class"])


# ---------- Lifecycle: load the model ONCE at startup ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = None
    try:
        app.state.model = load_model()
        logger.info("model loaded", extra={"extra_fields": {"model_version": MODEL_VERSION}})
    except Exception:
        # Do not crash the process: /ready returns 503 and Kubernetes sends it no traffic
        logger.exception("model could not be loaded")
    yield


app = FastAPI(title="Claims Risk Service", version=MODEL_VERSION, lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    path = request.url.path
    if path != "/metrics":  # do not measure Prometheus' own scraping
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


# ---------- Schemas: input validation with Pydantic ----------
class ClaimRequest(BaseModel):
    claim_amount: float = Field(gt=0, description="Claim amount in EUR")
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
    """Liveness: is the process alive? If it fails, Kubernetes RESTARTS the pod."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: can it serve traffic? If it fails, Kubernetes REMOVES traffic (no restart)."""
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
    """Endpoint that Prometheus scrapes periodically."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

It was **not** written in one go. Build it in five layers, starting uvicorn after each one to check it works:

**Layer a — minimal skeleton.** `app = FastAPI()` and a `/health` endpoint returning `{"status": "ok"}`. Run `uvicorn app.main:app --reload`. If this does not work, nothing else matters.

**Layer b — load the model at startup.** `asynccontextmanager` (from `contextlib`) creates the `lifespan` function: code **before `yield`** runs **once at startup**. The model is loaded there and stored in `app.state.model`. Loading it per request would make every prediction much slower. If loading fails, the process does **not** crash — `model` stays `None`.

**Layer c — schemas and prediction.** `pydantic.BaseModel` + `Field` define `ClaimRequest`: what must arrive and within which limits (`gt=0`, `ge=0`, `le=...`). FastAPI validates automatically and returns **422** for invalid input. `RiskResponse` defines the output. Then `POST /predict` calls `predict_risk` from `model.py`.

**Layer d — readiness.** `/ready` returns **503** (`HTTPException`) when the model is not loaded. This creates the liveness vs. readiness split used later by Kubernetes:

| Endpoint | Question it answers | If it fails, Kubernetes… |
|---|---|---|
| `/health` (liveness) | Is the process alive? | **restarts** the container |
| `/ready` (readiness) | Can it serve traffic? | **stops sending it traffic** (no restart) |

**Layer e — observability**, added last because it is cross-cutting:

- `json` + `logging`: a `JsonFormatter` class turns every log record into one JSON line on **stdout** (containers never write log files; the platform collects stdout).
- `prometheus_client` (`Counter`, `Histogram`): three metrics — request count, latency, predictions per risk class.
- `@app.middleware("http")`: wraps **every** request. It measures duration with `time.perf_counter()`, updates the metrics and writes the log line, so no endpoint has to repeat this code.
- `/metrics` returns `generate_latest()`: the text format Prometheus scrapes.

### 4.7 Tests

**`tests/conftest.py`** — pytest loads this file **automatically**:

```python
import pytest
from fastapi.testclient import TestClient

from app import train
from app.model import MODEL_PATH


@pytest.fixture(scope="session")
def client():
    if not MODEL_PATH.exists():  # in CI there is no model yet: train it before testing
        train.main()
    from app.main import app

    with TestClient(app) as c:  # the "with" triggers the lifespan (model loading)
        yield c
```

**`tests/test_api.py`**:

```python
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
    assert r.status_code == 422  # Pydantic validation


def test_riskier_claim_scores_higher(client):
    """Tests model behaviour, not just the API."""
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
```

How pytest works here:

- **Discovery by name**: it collects files `test_*.py`, functions `test_*` and classes `Test*` under `testpaths`. Rename `test_health` to `check_health` and it silently disappears.
- **Fixture injection by name**: `def test_health(client)` — pytest reads the parameter name `client`, finds the fixture with that name in `conftest.py`, runs it and passes the result.
- `scope="session"`: the fixture runs **once** for all tests (the model is trained/loaded once).
- Code **before `yield`** = setup; **after** = teardown.
- `with TestClient(app)` is essential: without it, the `lifespan` does not run and the model is never loaded.
- Plain `assert`: pytest rewrites it to show the actual values on failure.
- `test_riskier_claim_scores_higher` tests the **model's behaviour**, not just the API.

### 4.8 `pyproject.toml` — tool configuration

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B"]  # pycodestyle, pyflakes, imports ordenados, bugbear

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Ruff looks for `pyproject.toml` starting in the current folder and walking up. The rule families:

| Code | Source | Catches |
|---|---|---|
| `E` | pycodestyle | Style: long lines, whitespace |
| `F` | pyflakes | Real errors: unused imports, undefined names |
| `I` | isort | Import ordering |
| `B` | bugbear | Patterns that often cause bugs |

**`ruff check` and `ruff format` are two different tools** — a lesson learned the hard way in CI:

| Command | What it does | Used by CI |
|---|---|---|
| `ruff check .` | Finds **errors** (unused imports, undefined names…) | ✅ |
| `ruff check . --fix` | Fixes the **errors** it can | — |
| `ruff format --check .` | Checks **style** without changing anything | ✅ |
| `ruff format .` | **Reformats** files | — |

`ruff check --fix` removes an unused import but does **not** reformat the file. Always run **both** checks before pushing.

### 4.9 `.gitignore`

```text
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
report.xml
# The model is produced at build time, it is not versioned
app/model.joblib
# Terraform: state NEVER goes to git (it can contain secrets)
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
terraform.tfvars
```

### 4.10 Run and verify

```bash
ruff check .            # errors
ruff format --check .   # style
pytest -v               # tests
python -m app.train     # train (AUC ≈ 0.84)
uvicorn app.main:app --reload
```

These are exactly the commands the CI pipeline will automate later.

Open **`http://127.0.0.1:8000/docs`** (Swagger UI) and try `POST /predict` with:

```json
{"claim_amount": 4500, "policy_age_years": 3, "prior_claims": 1, "days_to_report": 12}
```

Or with curl:

```bash
curl -s http://127.0.0.1:8000/ready
curl -s -X POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"claim_amount":4500,"policy_age_years":3,"prior_claims":1,"days_to_report":12}'
curl -s http://127.0.0.1:8000/metrics | grep -E "^(http_requests_total|predictions_total)"
```

Watch the terminal: every request produces one JSON log line.

### 4.11 Practice

- Send `"claim_amount": -10` → **422**: Pydantic validation, no extra code.
- `pytest --collect-only` → lists the tests found, without running them.
- `ruff check . --show-files` → lists the files ruff will check.
- Add `import sys` to `app/model.py` → `ruff check .` reports **F401**. Fix it with `ruff check . --fix`, then run `ruff format --check .` too.
- Rename `test_health` to `check_health` → `pytest --collect-only` shows one test fewer.

### 4.12 Troubleshooting

- **`GET /` returns 404** — not an error: there is no route at `/`. Use `/docs`, `/health`, `/ready`.
- **`WARNING: Invalid HTTP request received`** — usually the browser trying `https://`. Uvicorn speaks plain HTTP: use `http://`.
- **`{"detail": "model not loaded"}` although the log says `model loaded`** — the request went to **another process** on port 8000 (e.g. a leftover Docker container started with a wrong `MODEL_PATH`). `localhost` may resolve to IPv6 `::1`, where Docker listens, while uvicorn listens on `127.0.0.1`. Use `http://127.0.0.1:8000`, check `docker ps` / `lsof -i :8000`, or run uvicorn on another port (`--port 8001`).

### 4.13 Interview notes

- **Why separate liveness and readiness?** A service whose model failed to load is alive but must not receive traffic. Restarting it in a loop would not help; removing it from load balancing does.
- **Why load the model in the lifespan?** Loading once at startup avoids per-request latency; failures are surfaced through `/ready`, not through a crash.
- **Why JSON logs on stdout?** Containers are ephemeral; the platform (CloudWatch, Loki, Fluent Bit) collects stdout. JSON makes logs filterable (`status >= 500`, `duration_ms > 200`).
- **What metrics matter for an AI service?** Latency (p95/p99), error rate, throughput; for models also prediction distribution and **drift**; for LLM services also **cost per token**.

---

## 5. Phase 2 — Docker

### 5.1 Concepts

A virtualenv isolates Python libraries. Docker isolates **everything**: base OS, Python version, libraries, code and start command. The result runs identically on your Mac, on a GitLab runner and in a cloud cluster.

| Concept | Meaning |
|---|---|
| **Image** | Immutable, read-only template with everything needed to run the app (like a class). Built with `docker build`. |
| **Container** | A running instance of an image (like an object). Created with `docker run`. What it writes disappears when it is removed. |
| **Layer** | Each Dockerfile instruction creates a layer. Layers are cached and reused if nothing changed. |
| **Registry** | "GitHub for images": Docker Hub, GitLab Container Registry, AWS ECR. `docker push` / `docker pull`. |
| **Daemon** | The background process that does the real work. The `docker` command is only a client. On macOS the daemon lives inside **Docker Desktop**, which must be running. |

### 5.2 `Dockerfile`

```dockerfile
# =============================================================
# Multi-stage build
#  Stage 1 (builder): installs dependencies and trains the model.
#  Stage 2 (runtime): copies only what is needed to run.
#  Result: smaller final image with a smaller attack surface
#  (no compilers, no pip cache, no leftover build artefacts).
# =============================================================

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# Virtualenv at a fixed path so it can be copied as a whole into stage 2
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements.txt FIRST: if it does not change, Docker reuses the cached
# layer and does not reinstall dependencies on every build (much faster builds).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the code (changes often -> goes later)
COPY app/ app/
RUN python -m app.train


# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

# Unprivileged user: if the app is compromised, the attacker is not root in the container
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/app ./app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 8000

# Exec form (JSON array): uvicorn is PID 1 and receives SIGTERM for a clean shutdown
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Stage 1 — `builder` (the workshop):**

- `FROM python:3.12-slim AS builder` — official Debian-slim image with Python 3.12 (~150 MB vs ~1 GB for the full image). `AS builder` names the stage.
- `WORKDIR /build` — creates the folder inside the image and moves into it (`mkdir` + `cd`).
- `RUN python -m venv /opt/venv` + `ENV PATH=...` — `RUN` executes **at build time** and the result is stored in the layer. The venv puts all dependencies in **one folder** that can be copied whole into stage 2.
- `COPY requirements.txt .` then `RUN pip install ...` — **the most important decision in the file.** Docker rebuilds a layer if its instruction **or the files it copies** change, and then rebuilds **every later layer**. Code changes many times a day; requirements rarely. Copying requirements first keeps the slow `pip install` layer cached. `--no-cache-dir` avoids storing pip's download cache in the image.
- `COPY app/ app/` + `RUN python -m app.train` — now the code, then training **during the build**: `/build/app/model.joblib` ends up inside the image.

**Stage 2 — `runtime` (what ships):**

- `FROM python:3.12-slim AS runtime` — a **clean start**. Nothing from stage 1 comes along unless explicitly copied. The final image is only this stage.
- `RUN useradd --create-home --uid 10001 appuser` — containers run as **root** by default; a compromised app would have root inside the container. UID 10001 matches `runAsUser` in the Kubernetes manifest.
- `COPY --from=builder ...` — copies **from stage 1**, not from your Mac: only the venv and the `app` folder with the trained model. The venv works after copying because both stages use the same base image and the same path.
- `ENV PYTHONUNBUFFERED=1` — logs are written immediately, not buffered (otherwise `docker logs` / `kubectl logs` may show nothing for a while). `PYTHONDONTWRITEBYTECODE=1` — no `.pyc` files, required because Kubernetes will mount the filesystem **read-only**.
- `USER 10001` — everything from here on, including the app, runs as `appuser`.
- `EXPOSE 8000` — **documentation only**. It opens nothing; `-p` in `docker run` does. A classic interview question.
- `CMD [...]` — the command run **when the container starts** (not at build time — that is the difference with `RUN`).
  - `--host 0.0.0.0`: listen on all interfaces. With uvicorn's default `127.0.0.1` it would only accept connections from *inside* the container.
  - **Exec form** (JSON array) vs **shell form** (`CMD uvicorn ...`): in exec form uvicorn is PID 1 and receives `SIGTERM` directly, shutting down cleanly. In shell form the signal goes to an intermediate `sh` that does not forward it, and Docker kills the process after 10 seconds.

### 5.3 `.dockerignore` and the build context

In `docker build -t name .`, the final `.` is the **build context**: the folder your machine **sends in full to the daemon** before building. `COPY` can only take files from there.

```text
# What is NOT sent to the build context: smaller image, no junk or secrets
.git
.venv
__pycache__
.pytest_cache
.ruff_cache
tests
infra
k8s
*.md
app/model.joblib
```

It keeps `.venv` (hundreds of MB), `.git`, tests and infra out of the context. It also excludes `app/model.joblib`, guaranteeing the model is **always trained inside the build** and a stale local model never sneaks in — reproducibility.

### 5.4 Practice

Check the daemon first: `docker version` must show both **Client** and **Server**.

**Exercise 1 — first build and the cache**

```bash
docker build -t claims-risk-service:local .
```

`-t` sets `name:tag`. The output shows both stages (`[builder 5/7] RUN pip install...`, `[runtime 4/7] COPY --from=builder...`) and the AUC printed by training. Run the **same command again**: it takes a second, every step says `CACHED`. Now edit a comment in `app/main.py` and rebuild: `pip install` stays `CACHED`, `COPY app/` and everything after it reruns. **That is why instruction order matters.**

**Exercise 2 — inspect the image**

```bash
docker images claims-risk-service
docker history claims-risk-service:local
docker image inspect claims-risk-service:local --format '{{.Architecture}}'
```

The heaviest layer is the venv (scikit-learn, numpy, scipy). On an Apple Silicon Mac the architecture is **`arm64`**. Many cloud nodes are **`amd64`**, and an arm64 image does not start there. That is why images are built in CI (GitLab runners are amd64) or with `docker buildx build --platform linux/amd64`.

**Exercise 3 — run the container**

```bash
docker run --rm -p 8000:8000 --name claims claims-risk-service:local
```

- `-p 8000:8000` = `host_port:container_port`. Try `-p 9000:8000` → app on `127.0.0.1:9000`.
- `--rm` removes the container when it stops.
- `--name` gives it a name.

Open `http://127.0.0.1:8000/docs`.

**Exercise 4 — operate a running container** (second terminal)

```bash
docker ps
docker logs -f claims
docker exec -it claims sh
  whoami             # appuser, not root
  ls -la /app/app    # code + model.joblib
  touch /app/test    # Permission denied
  exit
```

`docker exec` is the main debugging tool; its Kubernetes equivalent is `kubectl exec`.

**Exercise 5 — graceful shutdown**

```bash
time docker stop claims
```

Under a second: uvicorn receives `SIGTERM`. With shell-form `CMD` it would take ~10 s. In Kubernetes this matters on every deployment: old pods must stop without cutting in-flight requests.

**Exercise 6 — configuration without rebuilding**

```bash
docker run --rm -p 8000:8000 -e MODEL_VERSION=0.2.0 -e LOG_LEVEL=WARNING claims-risk-service:local
```

`/ready` shows version `0.2.0`, and request logs disappear (they are INFO, the threshold is now WARNING). **One image for every environment**, configuration injected from outside — exactly what the ConfigMap does in Kubernetes.

**Exercise 7 — simulate a readiness failure**

```bash
docker run --rm -p 8000:8000 -e MODEL_PATH=/does/not/exist claims-risk-service:local
```

The log shows `model could not be loaded`, but the process stays up: `/health` → **200**, `/ready` → **503**. This is exactly the situation where Kubernetes does **not** restart the pod but does **not** send it traffic. Stop it afterwards (`Ctrl+C`) so it does not keep port 8000 busy.

**Cleanup**

```bash
docker system df
docker image prune
```

### 5.5 Interview notes

- **Image vs. container** — immutable template vs. running instance.
- **RUN vs. CMD** — build time vs. container start.
- **CMD vs. ENTRYPOINT** — `ENTRYPOINT` fixes the executable; `CMD` provides default arguments, easy to override.
- **COPY vs. ADD** — always `COPY`. `ADD` also unpacks tar files and downloads URLs: implicit behaviour better avoided.
- **Why multi-stage?** Smaller image, smaller attack surface: build tools never reach production.
- **Why non-root?** Limits damage if the app is compromised. Many enterprise clusters **reject** root pods (Pod Security Standards).
- **Secrets?** **Never** in the image — not in `ENV`, `COPY` or `ARG`: they stay in the layers and `docker history` reveals them. Inject at runtime (AWS Secrets Manager, Kubernetes Secrets). For build-time secrets: `RUN --mount=type=secret`.
- **Which tag?** The commit SHA, not `latest`: traceability. That is why the ECR repository is `IMMUTABLE`.
- **How to shrink an image?** Multi-stage, slim/distroless base, `.dockerignore`, `--no-cache-dir`, fewer dependencies.
- **Image security?** Vulnerability scanning (ECR scan-on-push, Trivy in the pipeline) and regular base image updates.

---

## 6. Phase 3 — GitLab CI

### 6.1 Concepts

**A CI pipeline automates what you would do by hand.** In Phase 1 you ran `ruff`, then `pytest`; in Phase 2, `docker build`. The pipeline does exactly that, in the same order, on clean machines, on every push. Nobody skips a step.

On every push GitLab checks for **`.gitlab-ci.yml`** at the repo root. If it exists, a pipeline starts. A pipeline is always tied to **one specific commit**.

| Concept | Meaning |
|---|---|
| **Pipeline** | One full run, triggered by an event (push, merge request, schedule) |
| **Stage** | A phase. Stages run **in order**; if one fails, the next ones do not start |
| **Job** | A task inside a stage. Jobs in the same stage run **in parallel** |
| **Runner** | The machine executing jobs. GitLab.com offers free *shared runners*; companies usually run *self-hosted* runners, often on Kubernetes |
| **`image`** | Each job starts a **fresh container** from this image. Every job is a disposable `docker run` |
| **`script`** | The job's commands. If **any** returns a non-zero exit code, the job fails (that is how `pytest` tells GitLab a test failed) |
| **Variables** | **Predefined** (injected by GitLab: commit, branch, registry credentials…) or **custom** (in the file or *Settings → CI/CD → Variables*, optionally *masked* and *protected*) |
| **cache** | Speeds up *future* jobs (e.g. pip downloads). Disposable |
| **artifacts** | *Results* of a job kept or passed to other jobs (e.g. a test report) |
| **`rules`** | Conditions deciding whether a job runs |
| **`needs`** | Lets a job start as soon as its dependencies finish, turning the pipeline into a DAG |

Stage and job names are **free labels**. `stages: [a, b, c, d]` would work just as well; only the **order of the list** and the match with each job's `stage:` matter. Descriptive names are used because they appear in the UI. Details: without `stages`, GitLab uses `build`, `test`, `deploy`; a job without `stage:` goes to `test`; `.pre` and `.post` are reserved and always run first/last. Job names cannot be reserved keywords (`image`, `variables`, `stages`, `cache`, `default`…), and a name starting with a dot makes a **hidden template**.

### 6.2 Set up GitLab

1. **Create an account** on gitlab.com and **verify your identity** (phone or card, nothing is charged). Without verification, shared runners never pick up your jobs (they stay *pending*).
2. **Create the project**: *New project → Create blank project*, name `claims-risk-service`, visibility *Private*, and **untick "Initialize repository with a README"** (otherwise the histories diverge and the push fails).
3. **Create a Personal Access Token** — GitLab does not accept your password for `git push` over HTTPS: avatar → *Edit profile → Access tokens → Add new token*, scopes **`write_repository`** and **`read_registry`**. Copy it now; it is shown only once.
4. **Add GitLab as a second remote** (`origin` stays GitHub):

```bash
git remote add gitlab https://gitlab.com/YOUR_GITLAB_USER/claims-risk-service.git
git remote -v
git branch                        # make sure the branch is "main"
git push gitlab main              # username = GitLab user, password = the TOKEN
```

The macOS keychain stores the token. From now on push to both:

```bash
git push gitlab main && git push origin main
```

5. **Watch the pipeline**: project sidebar → *Build → Pipelines*, or directly `https://gitlab.com/YOUR_GITLAB_USER/claims-risk-service/-/pipelines`.

### 6.3 `.gitlab-ci.yml`

```yaml
# =====================================================================
# Pipeline: lint -> test -> build -> infra
# Each "job" runs in a clean container (image:) on a GitLab runner.
# If a stage fails, the following ones do not run: broken code never becomes an image.
# =====================================================================

stages:
  - lint
  - test
  - build
  - infra

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  IMAGE_TAG: "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA"   # tag = commit -> traceability

# pip cache between pipelines: faster (and cheaper) jobs
.python_job:
  image: python:3.12-slim
  cache:
    key:
      files: [requirements.txt, requirements-dev.txt]   # invalidated when dependencies change
    paths: [.cache/pip]

# ---------------------------------------------------------------------
lint:
  extends: .python_job
  stage: lint
  script:
    - pip install ruff==0.16.8
    - ruff check .
    - ruff format --check .

# ---------------------------------------------------------------------
test:
  extends: .python_job
  stage: test
  script:
    - pip install -r requirements.txt -r requirements-dev.txt
    - pytest -v --junitxml=report.xml
  artifacts:
    when: always
    reports:
      junit: report.xml          # GitLab shows the tests in the pipeline/MR tab

# ---------------------------------------------------------------------
# Build the image and push it to GitLab's built-in Container Registry.
# Docker-in-Docker (dind): the job starts a Docker daemon as a "service".
build:
  stage: build
  image: docker:27
  services:
    - docker:27-dind
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
  before_script:
    # CI_REGISTRY_* are predefined variables: GitLab injects them into every job
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
  script:
    - docker build -t "$IMAGE_TAG" .
    - docker push "$IMAGE_TAG"
    - |
      if [ "$CI_COMMIT_BRANCH" = "$CI_DEFAULT_BRANCH" ]; then
        docker tag "$IMAGE_TAG" "$CI_REGISTRY_IMAGE:latest"
        docker push "$CI_REGISTRY_IMAGE:latest"
      fi

# ---------------------------------------------------------------------
# Push to AWS ECR authenticating via OIDC (no access keys stored in GitLab).
# Runs only on main AND if you have defined AWS_ROLE_ARN and ECR_REGISTRY
# in Settings > CI/CD > Variables (values from the Terraform outputs).
push_ecr:
  stage: build
  image: docker:27
  services:
    - docker:27-dind
  needs: [test]
  id_tokens:
    AWS_OIDC_TOKEN:
      aud: sts.amazonaws.com       # must match client_id_list of the OIDC provider
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
    AWS_REGION: eu-central-1
    AWS_WEB_IDENTITY_TOKEN_FILE: /tmp/web_identity_token
  before_script:
    - apk add --no-cache aws-cli
    - echo "$AWS_OIDC_TOKEN" > "$AWS_WEB_IDENTITY_TOKEN_FILE"
    # The AWS CLI detects AWS_ROLE_ARN + AWS_WEB_IDENTITY_TOKEN_FILE and assumes the role itself
    - aws sts get-caller-identity
    - aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY"
  script:
    - docker build -t "$ECR_REGISTRY/claims-risk-service:$CI_COMMIT_SHORT_SHA" .
    - docker push "$ECR_REGISTRY/claims-risk-service:$CI_COMMIT_SHORT_SHA"
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH && $AWS_ROLE_ARN && $ECR_REGISTRY'

# ---------------------------------------------------------------------
# Validation of the infrastructure code (no AWS credentials needed).
# In a real team this would also run "terraform plan" on every MR
# and "terraform apply" with manual approval (when: manual) on main.
terraform_validate:
  stage: infra
  image:
    name: hashicorp/terraform:1.9
    entrypoint: [""]
  needs: []                        # does not depend on earlier stages: runs in parallel
  script:
    - cd infra
    - terraform fmt -check -recursive
    - terraform init -backend=false
    - terraform validate
  rules:
    - changes: [infra/**/*]        # only if something under infra/ changed
```

**Header**

- `stages` — declares the phases and their order.
- `variables` — available to every job. `PIP_CACHE_DIR` must be **inside** the project (`$CI_PROJECT_DIR`) because GitLab only caches paths there. `IMAGE_TAG` combines two predefined variables: `$CI_REGISTRY_IMAGE` (e.g. `registry.gitlab.com/user/claims-risk-service`) and `$CI_COMMIT_SHORT_SHA` (e.g. `a1b2c3d4`) → every image is tied to an exact commit.

**`.python_job` template** — a job starting with a dot is never executed; others inherit it with `extends` (DRY). Its cache key is computed from the requirement files: same dependencies → same cache; change `requirements.txt` → new cache. Same logic as Docker layer caching.

**`lint`** — installs only ruff (same pinned version as `requirements-dev.txt`, otherwise lint could pass locally and fail in CI) and runs both checks.

**`test`** — installs everything and runs pytest. `conftest.py` trains the model because the clean container has no `model.joblib`. `--junitxml=report.xml` writes a standard report; `artifacts.reports.junit` makes GitLab display the tests in the pipeline's **Tests** tab and in merge requests; `when: always` uploads it **even when tests fail** — when you need it most.

**`build`** — the job already runs inside a container and must build a Docker image. Solution: **Docker-in-Docker**. `image: docker:27` provides the **client**; `services: docker:27-dind` starts a second container with a **daemon**; `DOCKER_TLS_CERTDIR` encrypts their communication. `before_script` logs into the registry with **temporary per-job credentials** (`CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD`) — no password stored anywhere. `--password-stdin` keeps the password out of logs and the process list. The image is always pushed with the commit tag; only on `main` is it also tagged `latest`, so `latest` always means "latest main".

**`push_ecr`** — the OIDC pattern to AWS (explained in Phase 4). Its `rules` require `main` **and** the variables `AWS_ROLE_ARN` and `ECR_REGISTRY`. Until they exist, the job simply does not appear — the job lives in code but activates only when the infrastructure is ready.

**`terraform_validate`** — `entrypoint: [""]` overrides the Terraform image's `ENTRYPOINT` (which is `terraform` itself) because GitLab needs a shell. `needs: []` starts it immediately, in parallel with `lint`. `rules: changes` runs it only when `infra/` changes. `init -backend=false` downloads providers without configuring remote state — no AWS access needed to validate syntax.

### 6.4 Practice

**Exercise 1 — read a job log.** Open the `test` job and find: pulling the image → getting the source → restoring cache → your commands (each prefixed with `$`) → saving cache / uploading artifacts → `Job succeeded`. Reading this log is the key debugging skill.

**Exercise 2 — see the cache.** *Build → Pipelines → Run pipeline* on `main` and compare the `test` duration: the second run restores the pip cache.

**Exercise 3 — break the lint.** Add `import sys` to `app/model.py`, commit, push. `lint` fails with `F401`, and `test` / `build` are **skipped**: broken code never becomes an image. Fix it (`ruff check . --fix` **and** `ruff format .`), commit, push.

**Exercise 4 — branch + merge request (the team workflow).**

```bash
git checkout -b feature/test-mr
# make an assert fail in tests/test_api.py
git commit -am "Failing test on purpose"
git push gitlab feature/test-mr
```

Create the MR from GitLab's banner. The MR shows the pipeline and a **test widget** naming the failed test; `build` never runs. Fix and push again: the pipeline reruns and the MR turns green. On a branch, the image is pushed **only with the commit tag**, never as `latest`.

Close the MR without merging: *Code → Merge requests* → open it → **⋮** (next to *Edit*) → **Close merge request**. Shortcut: comment `/close` (a GitLab *quick action*). Then clean up:

```bash
git checkout main
git branch -D feature/test-mr              # -D: the branch was never merged
git push gitlab --delete feature/test-mr
```

**Exercise 5 — pull your image from the registry.** *Deploy → Container Registry* shows your tags.

```bash
docker login registry.gitlab.com          # user + token
docker pull registry.gitlab.com/YOUR_GITLAB_USER/claims-risk-service:latest
docker image inspect registry.gitlab.com/YOUR_GITLAB_USER/claims-risk-service:latest --format '{{.Architecture}}'
```

It says **`amd64`** (built on GitLab's runners), unlike your local **`arm64`** image. On an Apple Silicon Mac it still runs, through emulation.

**Exercise 6 — validate YAML before pushing.** *Build → Pipeline editor* validates the file live; the *Visualize* tab draws the stage/job graph. Indentation is error number one.

### 6.5 Troubleshooting (real cases)

- **No pipeline appears at all** → `.gitlab-ci.yml` is missing from the repo (hidden file not copied). Check `ls -la` and `git ls-files | grep gitlab-ci`. Also check CI/CD is enabled: *Settings → General → Visibility, project features, permissions → CI/CD*.
- **The `.venv` or `model.joblib` got committed** because `.gitignore` was missing → `git rm -r --cached .venv app/model.joblib`, commit, push.
- **`lint` fails with `File would be reformatted` although `ruff check` passes locally** → it is `ruff format --check` failing, not `ruff check`. Reproduce it locally with `ruff format --check .`, fix with `ruff format .`, verify, commit, push.
- **`nothing to commit, working tree clean`** → no pending changes; not an error. `Your branch is ahead of 'origin/main' by N commits` refers only to `origin`. To see what GitLab is missing: `git fetch gitlab && git log --oneline gitlab/main..main`.
- **`Everything up-to-date` and no new pipeline** → GitLab creates pipelines only for **new commits**. Compare `git log -1 --oneline` with the SHA shown on the latest pipeline. To trigger one anyway: *Run pipeline* in the UI, or `git commit --allow-empty -m "Trigger CI" && git push gitlab main`.
- **Jobs stuck in *pending*** → identity not verified, or shared runners disabled (*Settings → CI/CD → Runners → Enable instance runners for this project*).
- **Push rejected / authentication failed** → the password must be the **token**, not your GitLab password.

### 6.6 Interview notes

- **Runner types** — shared vs. self-hosted. Enterprises use self-hosted runners inside their network, often with the **Kubernetes executor** (each job is a pod).
- **cache vs. artifacts** — disposable speed-up vs. results kept or passed on.
- **Secrets in CI** — masked + protected variables at minimum; better **OIDC** (no stored credentials) or a secret manager (Vault, AWS Secrets Manager). Never in the repository.
- **Faster pipelines** — dependency caching, `needs` for parallelism, small base images, Docker layer caching, `rules` to skip unchanged parts.
- **Docker-in-Docker drawbacks** — needs **privileged** runners, often forbidden in enterprises. Alternatives: **Kaniko**, **Buildah** (daemonless, unprivileged builds).
- **Reusing pipelines across teams** — `include`: a central platform team publishes templates (standard build, security scanning) that projects import.
- **Deploying to production** — `environments`, protected environments and a `when: manual` approval job. With Kubernetes, typically **GitOps**: CI builds the image and updates the tag in a manifest/Helm repo; **ArgoCD** detects the change and syncs the cluster. CI never touches the cluster directly.
- **Avoiding trivial pipeline failures** — **pre-commit hooks** (the `pre-commit` framework) run ruff on every `git commit`; CI remains the safety net.
- **A red pipeline on main** — blocks deployment and is fixed immediately; `main` must always be deployable. Work happens in branches with MRs that must be green before merging.

---

## 7. Phase 4 — Terraform on AWS

### 7.1 Concepts

**Declarative infrastructure.** Without Terraform you create resources by clicking in the console or running loose CLI commands — *imperative*: "create a bucket, then enable versioning, then…". Nobody knows later what was done, in which order or why, and replicating it elsewhere is manual. With Terraform you **describe the desired final state** ("a bucket with versioning and encryption"); Terraform compares it with reality and computes what to create, change or delete. It is **idempotent**: run it ten times with the same code, the first run creates, the other nine do nothing.

| Concept | Meaning |
|---|---|
| **Provider** | Plugin that talks to one API (AWS, Azure, GitLab, Kubernetes…) |
| **Resource** | Something Terraform **creates and manages**. Remove it from the code and Terraform **deletes** it |
| **Data source** | Something Terraform **only reads** (e.g. GitLab's TLS certificate, a generated IAM policy document) |
| **Variable** | Input parameter |
| **Output** | Value returned after apply |
| **State** | `terraform.tfstate`: the map between code and real resources |

**The state is Terraform's memory.** Without it, Terraform would not know which resources it created and would try to create them again. Therefore:

- never delete or edit it by hand;
- **never commit it to git** (it can contain sensitive data in plain text);
- in a team it lives **remotely** (S3) with **locking**, so two people or pipelines cannot apply changes at the same time.

**The workflow**

```
terraform init      → download providers, prepare the directory (and the backend)
terraform fmt       → canonical formatting (CI checks it)
terraform validate  → syntax and references (no AWS access)
terraform plan      → compare code vs. reality and SHOW what would change (changes nothing)
terraform apply     → EXECUTE the plan (asks for confirmation)
terraform destroy   → delete everything this code manages
```

`plan` is the safety net: a reviewable dry-run. In a team, `plan` runs on every merge request; `apply` runs after approval.

**Dependency graph.** You never state the order. Terraform infers it from **references**: if the IAM role mentions `aws_iam_openid_connect_provider.gitlab.arn`, the provider must be created first. Independent resources are created **in parallel**; `destroy` follows the graph in reverse.

**Terraform vs. CDK vs. CloudFormation**

- **CloudFormation** — AWS-native IaC in YAML/JSON; AWS manages the state.
- **AWS CDK** — infrastructure in a programming language (Python, TypeScript…) that **synthesises CloudFormation** (`cdk synth`). Loops, classes, tests — AWS only.
- **Terraform** — its own declarative language (HCL) and its own state; **multi-provider** (AWS, Azure, GitLab, Kubernetes, Datadog…). The most widespread in large companies.

The concepts transfer between them: declarative desired state, plan before apply, reusable modules.

**Where Terraform fits with the other tools** — Terraform/CDK and Kubernetes do not compete; they work in layers:

```
Terraform / CDK   → builds the infrastructure: network (VPC), EKS cluster, ECR, S3, IAM…
Kubernetes (EKS)  → runs and keeps the containers alive inside the cluster
Helm / ArgoCD     → deploy the application into Kubernetes
Docker            → packages the application into an image
```

### 7.2 Prepare the AWS account and CLI

Use a **personal** AWS account, never a corporate one.

1. **Create an IAM user for the CLI** (never create access keys for the **root** user): *IAM → Users → Create user* → name `terraform-learn` (no console access needed).
2. **Attach permissions**: *Permissions → Add permissions → Attach policies directly* → **`AdministratorAccess`**. Acceptable for a learning account; in real environments the user would have least-privilege permissions.
3. **Create an access key**: user → *Security credentials → Create access key* → use case *Command Line Interface (CLI)*. Copy the ID and secret (shown once).
4. **Configure the CLI**:

```bash
aws configure
#   AWS Access Key ID:     <paste>
#   AWS Secret Access Key: <paste>
#   Default region name:   eu-central-1
#   Default output format: json
#   Configure AWS skills and the AWS MCP server for your AI coding agent(s)? → n
aws sts get-caller-identity       # your account + arn:...:user/terraform-learn
```

Credentials land in `~/.aws/credentials`, outside the repo; Terraform finds them there by convention. Answer **`n`** to the AI-agent/MCP question: an agent would use these administrator credentials.

5. **Zero-spend budget** (2 minutes, recommended): *Billing and Cost Management → Budgets → Create budget → Zero spend budget*.

> A static access key in a file is exactly the problem **OIDC** solves in CI: it never expires and grants access until someone deletes it. Acceptable on a personal laptop; companies use **IAM Identity Center (SSO)** with `aws sso login` (temporary credentials). In pipelines: never — use OIDC. Deactivate the key when you finish practising.

### 7.3 The files

Terraform reads **all `*.tf` files in the folder as one**. Splitting them into `versions.tf`, `variables.tf`, `main.tf`, `outputs.tf` is pure convention for readability.

#### `infra/versions.tf`

```hcl
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
```

- `required_version` — an older Terraform fails with a clear message instead of misbehaving.
- `source` — where to download the provider (Terraform Registry).
- `version = "~> 5.0"` — any 5.x, never 6.0. Major versions may break compatibility; you decide when to jump.
- `tls` — used to read GitLab's certificate (see OIDC below).

`terraform init` generates **`.terraform.lock.hcl`** with the exact provider versions. **Commit it**: it guarantees the whole team and CI use identical versions (same idea as pinning `requirements.txt`).

#### `infra/backend.tf`

```hcl
# ------------------------------------------------------------------
# REMOTE STATE (always in a real team):
# The state is the "map" between this code and the real AWS resources.
# A local state only works for one person. In a team it lives in S3 with
# locking, so two pipelines cannot change the infrastructure at the same time.
#
# By default this project uses a local state. To enable the remote backend,
# create the bucket first (see BUILD_GUIDE.md, section 7.8) and uncomment:
#
# terraform {
#   backend "s3" {
#     bucket       = "YOUR-TERRAFORM-STATE-BUCKET"
#     key          = "claims-risk-service/terraform.tfstate"
#     region       = "eu-west-1"   # MUST be the region where the bucket lives
#     encrypt      = true
#     use_lockfile = true          # native S3 locking (Terraform >= 1.10); before: DynamoDB
#   }
# }
# ------------------------------------------------------------------
```

Commented out on purpose: without a `backend` block the state is local (`infra/terraform.tfstate`), which is enough to practise. Section 7.8 shows how to switch to S3. `use_lockfile` enables native S3 locking (Terraform ≥ 1.10); older projects use a **DynamoDB** table for locking — you will see that often.

#### `infra/variables.tf`

```hcl
variable "aws_region" {
  description = "AWS region for the resources"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Base name of the resources"
  type        = string
  default     = "claims-risk-service"
}

variable "owner" {
  description = "Owner (used in tags for cost allocation)"
  type        = string
  default     = "fernando"
}

variable "gitlab_project_path" {
  description = "GitLab project path, e.g. 'my-user/claims-risk-service'"
  type        = string
}
```

`gitlab_project_path` has **no default** → mandatory. Values are provided, in increasing priority, by: the `default`, a `terraform.tfvars` file (loaded automatically), `TF_VAR_name` environment variables, or `-var="name=value"`.

#### `infra/terraform.tfvars.example`

```hcl
# Copy this file to terraform.tfvars and set your GitLab project path (case-sensitive!)
gitlab_project_path = "YOUR_GITLAB_USER/claims-risk-service"
```

Convention: commit an example; each person creates a real `terraform.tfvars` (git-ignored). Real secrets should come from a secret manager, not from a file.

#### `infra/main.tf`

```hcl
provider "aws" {
  region = var.aws_region

  # Tags on ALL resources: allow filtering costs by project in Cost Explorer
  default_tags {
    tags = {
      Project   = var.project_name
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}

# =====================================================================
# 1) ECR: private registry for Docker images
# =====================================================================
resource "aws_ecr_repository" "app" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE" # a tag (commit SHA) cannot be overwritten: traceability
  force_delete         = true        # demo only: allows destroy with images inside

  image_scanning_configuration {
    scan_on_push = true # vulnerability (CVE) scan on every push
  }
}

# Cost control: keep only the last 10 images
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# =====================================================================
# 2) S3: bucket for model artefacts (private, encrypted, versioned)
# =====================================================================
resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${var.project_name}-artifacts-" # AWS appends a unique suffix
  force_destroy = true                             # demo only
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled" # allows rolling back to a previous model version
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# =====================================================================
# 3) OIDC: GitLab CI authenticates to AWS WITHOUT access keys
#    GitLab issues a signed token per job -> AWS verifies it ->
#    returns temporary credentials (1 h) for a specific role.
#    Note: only ONE provider per URL can exist in an AWS account.
# =====================================================================
data "tls_certificate" "gitlab" {
  url = "https://gitlab.com"
}

resource "aws_iam_openid_connect_provider" "gitlab" {
  url             = "https://gitlab.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.gitlab.certificates[0].sha1_fingerprint]
}

# Trust policy: WHO may assume the role -> only the main branch of YOUR project
data "aws_iam_policy_document" "gitlab_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.gitlab.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "gitlab.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "gitlab.com:sub"
      values   = ["project_path:${var.gitlab_project_path}:ref_type:branch:ref:main"]
    }
  }
}

resource "aws_iam_role" "gitlab_ci" {
  name               = "${var.project_name}-gitlab-ci"
  assume_role_policy = data.aws_iam_policy_document.gitlab_trust.json
}

# Permission policy: WHAT the role may do -> least privilege
data "aws_iam_policy_document" "gitlab_ci_permissions" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"] # this action cannot be restricted by resource
    resources = ["*"]
  }

  statement {
    sid = "EcrPushThisRepoOnly"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.app.arn]
  }

  statement {
    sid       = "ArtifactsReadWrite"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/*"]
  }

  statement {
    sid       = "ArtifactsList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
  }
}

resource "aws_iam_role_policy" "gitlab_ci" {
  name   = "least-privilege"
  role   = aws_iam_role.gitlab_ci.id
  policy = data.aws_iam_policy_document.gitlab_ci_permissions.json
}
```

**Provider and tags.** `var.aws_region` references a variable. `default_tags` adds the tags to **every** resource: filter costs by project/owner in **Cost Explorer**, and `ManagedBy = terraform` warns anyone in the console not to change it by hand.

**ECR.** Syntax: `resource "TYPE" "LOCAL_NAME"`. The type comes from the provider; the local name exists only inside Terraform and is referenced as `aws_ecr_repository.app`.
- `IMMUTABLE` — a tag like `a1b2c3d` can never be overwritten: a commit tag always points to the same image.
- `force_delete` — allows destroying the repo with images inside (demo only).
- `scan_on_push` — CVE scan on every push.

**Lifecycle policy.** `aws_ecr_repository.app.name` is a **reference** — it tells Terraform to create the repository first. `jsonencode()` is a Terraform **function** converting HCL into the JSON AWS expects. The policy keeps only the last 10 images: without it, storage grows forever (cost control).

**S3: one bucket, four resources.** Bucket names are unique **across all of AWS**; `bucket_prefix` lets AWS append a unique suffix. `"${...}"` is **interpolation**. Since AWS provider v4, each aspect of a bucket is its own resource, linked via `bucket = aws_s3_bucket.artifacts.id`:
- **public access block** — the bucket can never be made public, even by mistake (the number one cause of AWS data leaks);
- **versioning** — recover a previous model after a bad upload;
- **encryption** — at rest; non-negotiable for regulated industries.

**OIDC — the key security pattern.** The problem: to push images to ECR, GitLab CI needs AWS credentials. The old way — an IAM user with a stored access key — means a key that never expires, must be rotated by hand, and grants permanent access if leaked. The solution:

```
1. The GitLab job starts and GitLab hands it a signed token (JWT) stating:
   "I am a job of project user/claims-risk-service, branch main"
2. The job presents the token to AWS STS, asking to assume a role
3. AWS verifies the signature with gitlab.com's public key
   (because gitlab.com is registered as a trusted identity provider)
4. AWS checks the token against the trust policy conditions
5. AWS returns TEMPORARY credentials (valid for 1 hour)
```

No secret is stored anywhere.

- `data "tls_certificate" "gitlab"` reads gitlab.com's certificate (data sources are referenced with the `data.` prefix).
- `client_id_list = ["sts.amazonaws.com"]` — the token's **audience**; it matches `aud: sts.amazonaws.com` in the `push_ecr` job.
- Only **one** OIDC provider per URL can exist in an account.

**Trust policy vs. permission policy** — the central IAM distinction:

- **Trust policy** — **who** may assume the role. The `sub` (subject) condition limits it to **your project and only the `main` branch**. Without it, **any project of any gitlab.com user** could assume your role — a real, frequent misconfiguration.
- **Permission policy** — **what** the role may do: ECR login, push **only to this repository**, read/write **only this bucket**. **Least privilege.** `ecr:GetAuthorizationToken` needs `resources = ["*"]` because AWS does not allow restricting that action by resource.

`aws_iam_policy_document` is a data source that generates the policy JSON from HCL — more readable than raw JSON, and validated by Terraform.

**IAM evaluation logic** (worth memorising): AWS **denies everything by default**. An action is allowed only if an explicit `Allow` exists in an **identity-based** policy (user/role) or a **resource-based** policy (e.g. a bucket policy) — and an explicit `Deny` always wins. Error messages tell you which layer is missing the permission.

#### `infra/outputs.tf`

```hcl
output "ecr_repository_url" {
  description = "ECR repository URL (ECR_REGISTRY = this value without the repo name)"
  value       = aws_ecr_repository.app.repository_url
}

output "artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "gitlab_ci_role_arn" {
  description = "Value for the AWS_ROLE_ARN variable in GitLab CI/CD"
  value       = aws_iam_role.gitlab_ci.arn
}
```

### 7.4 Practice — without AWS access

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# edit it: gitlab_project_path = "YOUR_GITLAB_USER/claims-risk-service"  (exact case!)
```

**Exercise 1 — init**

```bash
terraform init
ls -la          # .terraform/ (providers, git-ignored) and .terraform.lock.hcl (commit it)
```

**Exercise 2 — fmt and a green CI**

```bash
terraform fmt   # prints the files it reformatted
cd .. && git add infra/ && git commit -m "Terraform fmt and lock file" \
  && git push gitlab main && git push origin main && cd infra
```

`terraform_validate` runs because `infra/` changed and should be green. Same lesson as `ruff format`.

**Exercise 3 — validate, then break it**

```bash
terraform validate      # Success! The configuration is valid.
```

Change `aws_ecr_repository.app.name` to `aws_ecr_repository.appp.name` in the lifecycle policy → `validate` reports an undeclared resource. `validate` checks references and types without contacting AWS. Undo the change.

**Exercise 4 — the console**

```bash
terraform console
> var.project_name
> var.gitlab_project_path
> "${var.project_name}-artifacts-"
> "project_path:${var.gitlab_project_path}:ref_type:branch:ref:main"
> upper(var.owner)
> jsonencode({ name = "test", number = 10 })
> exit
```

The fourth line is the exact `sub` your trust policy accepts.

### 7.5 Practice — with AWS

Cost: cents (empty ECR and S3; IAM is free). Always finish with `destroy`.

**Exercise 5 — read a plan**

```bash
terraform plan
```

| Symbol | Meaning |
|---|---|
| `+` | create |
| `~` | update in place |
| `-` | destroy |
| `-/+` | **replace** (destroy and recreate) — on a bucket or a database this means **data loss** |

Expected: `Plan: 9 to add, 0 to change, 0 to destroy` (ECR repo, lifecycle policy, bucket + 3 configurations, OIDC provider, role, role policy). Data sources are not counted. `(known after apply)` marks values AWS decides at creation (ARNs, the final bucket name).

**Exercise 6 — apply and the state**

```bash
terraform apply                              # type "yes"
terraform output
terraform state list
terraform state show aws_ecr_repository.app
terraform apply                              # "No changes" → idempotency
```

If apply fails because a gitlab.com OIDC provider already exists in the account, import it or reuse it (only one per URL).

**Exercise 7 — drift**

```bash
aws ecr put-image-scanning-configuration \
  --repository-name claims-risk-service \
  --image-scanning-configuration scanOnPush=false \
  --region eu-central-1
terraform plan      # shows "~": reality no longer matches the code
terraform apply     # restores the declared state
```

Drift = changes made outside Terraform — the everyday problem of a grown enterprise environment.

**Exercise 8 — safe vs. destructive changes**

- `countNumber = 10` → `5` → `terraform plan` shows `~` (in-place, safe).
- Default `project_name` → `claims-risk-v2` → `terraform plan` shows `-/+` with **`# forces replacement`**: renaming an ECR repository recreates it and loses its images. **This is why plans are always reviewed.** Undo both changes without applying.

**Exercise 9 (optional) — activate `push_ecr` with OIDC**

1. GitLab → *Settings → CI/CD → Variables*:
   - `AWS_ROLE_ARN` = output `gitlab_ci_role_arn`
   - `ECR_REGISTRY` = output `ecr_repository_url` **without** `/claims-risk-service` (e.g. `123456789012.dkr.ecr.eu-central-1.amazonaws.com`)
2. *Run pipeline* on `main`. The `push_ecr` log shows `aws sts get-caller-identity` with the **assumed role** — no stored key.
3. Check the image in the ECR console.
4. Re-running on the **same commit** makes `push_ecr` fail: the tag exists and the repo is `IMMUTABLE`. Expected behaviour.
5. Delete both variables when done.

**Cleanup (mandatory after apply)**

```bash
terraform destroy       # type "yes"; resources are removed in reverse dependency order
```

Then deactivate or delete the `terraform-learn` access key if you no longer need it.

### 7.6 Troubleshooting (real cases)

- **`AccessDenied ... because no identity-based policy allows the s3:GetBucketLocation action`** → the IAM user has no policy attached. The ARN in the message (`arn:aws:iam::<account>:user/terraform-learn`) confirms it is the right account; the phrase *no identity-based policy allows* points to the user's permissions. Attach `AdministratorAccess` from the console with root or another admin (a user cannot grant itself permissions).
- **`403 Forbidden` on `HeadObject` during `terraform init` with an S3 backend** → typical causes: (1) the backend `region` differs from the bucket's region; (2) credentials from another account; (3) missing `s3:ListBucket` — S3 answers **403 instead of 404** for a non-existent object (the state does not exist yet on the first init) when you are not allowed to list the bucket. Diagnose:

```bash
aws sts get-caller-identity                                  # Account must own the bucket
aws s3api get-bucket-location --bucket YOUR-STATE-BUCKET     # bucket region
grep region backend.tf                                       # backend region
aws s3 ls s3://YOUR-STATE-BUCKET                             # can you list it?
```

  After fixing: `terraform init -reconfigure`.

### 7.7 Interview notes

- **What is the state and how is it managed in a team?** Map between code and real resources; **S3 with encryption and versioning plus locking** (DynamoDB or native lockfile); never in git.
- **Drift?** Changes made outside Terraform; detected by `plan`. Many teams run a scheduled daily `plan` in CI to alert on drift.
- **Terraform in CI/CD?** `fmt` + `validate` + `plan` on every MR (plan visible for review); `apply` on `main` with **manual approval**; credentials via **OIDC**.
- **Trust vs. permission policy** — who may assume vs. what they may do; `sub` restricted to project and branch.
- **Avoiding accidental deletion** — review plans (`-/+`, `forces replacement`), and `lifecycle { prevent_destroy = true }` on critical resources.
- **Reuse** — **modules** (e.g. a standard "secure bucket"), often published by a platform team.
- **Multiple environments** — same code, one variable file and one separate state per environment (different backend `key`, or separate folders).
- **Existing hand-made resources** — `terraform import` or `import` blocks adopt them into the state without recreating them.
- **Security of infrastructure code** — policy-as-code scanners such as **Checkov** or **tfsec** in the pipeline.
- **Backend region vs. provider region** — independent: the state can live in `eu-west-1` while resources are created in `eu-central-1`.

### 7.8 Switching to a remote S3 backend

1. Create the state bucket **outside** this Terraform code (chicken-and-egg: Terraform cannot store its state in a bucket it has not created yet):

```bash
aws s3api create-bucket --bucket YOUR-TERRAFORM-STATE-BUCKET \
  --region eu-west-1 --create-bucket-configuration LocationConstraint=eu-west-1
aws s3api put-bucket-versioning --bucket YOUR-TERRAFORM-STATE-BUCKET \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket YOUR-TERRAFORM-STATE-BUCKET \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

2. Uncomment the block in `backend.tf`, set `bucket` and a `region` **equal to the bucket's region**.
3. Re-initialise:

```bash
terraform init -reconfigure            # new, empty backend
# or, to move an existing local state into S3:
terraform init -migrate-state
```

4. Check: `aws s3 ls s3://YOUR-TERRAFORM-STATE-BUCKET/claims-risk-service/` shows `terraform.tfstate` after the next apply.

---

## 8. Phase 5 — Kubernetes with kind

### 8.1 Concepts

**Desired state and control loops.** Like Terraform, you declare the state you want. The difference: Terraform compares code and reality **when you run `plan`**; Kubernetes compares them **continuously, every few seconds, forever**. Declare "2 replicas", one dies at 3 a.m., a *controller* notices 1 ≠ 2 and creates another. Nobody intervenes. That is **self-healing**.

**Cluster architecture**

- **Control plane** (the brain):
  - **API server** — the entry point; everything, including `kubectl`, talks to it.
  - **etcd** — the database storing the desired state of the whole cluster.
  - **Scheduler** — decides on which node each new pod runs, based on available resources.
  - **Controllers** — the loops correcting differences between desired and actual state.
- **Nodes** (workers) — the machines running containers. Each runs the **kubelet**, which starts containers and executes the probes.

In **EKS**, AWS manages the control plane; you manage the nodes and your applications. **EKS is Kubernetes**, managed by AWS; the AWS alternative orchestrator is **ECS**.

**Objects used in this project**

| Object | Role |
|---|---|
| **Pod** | Smallest unit: one or more containers sharing a network. **Ephemeral** — may die any time; a new pod gets a new name and IP. Never created by hand |
| **Deployment** | "N replicas of this pod, with this configuration". Handles rolling updates and rollbacks. Creates a **ReplicaSet**, which keeps the exact pod count |
| **Service** | Stable IP and DNS name in front of changing pods. Load-balances **only across ready pods** |
| **ConfigMap** | Configuration outside the image: one image for every environment |

**Labels and selectors.** Objects are linked by **labels**, not names. Pods carry `app: claims-risk-service`; the Deployment and the Service select pods with that label. If labels do not match, the Service finds no pods and no traffic arrives — the most common beginner mistake.

**kind (Kubernetes IN Docker)** creates a real cluster on your Mac where **each node is a Docker container**. Same Kubernetes as production, disposable and free. Nodes have **their own image store**, separate from Docker Desktop's: a locally built image does not exist inside the cluster until you run `kind load`. In production, nodes pull images from a registry instead.

**kubectl** is the CLI for any cluster — kind, EKS or others.

### 8.2 Installation

Docker Desktop must be running.

```bash
brew install kind kubectl
kind version
kubectl version --client
```

### 8.3 The manifests

Every manifest has four parts:

```yaml
apiVersion: ...   # API version defining this object type
kind: ...         # object type (Deployment, Service, ConfigMap…)
metadata: ...     # name and labels
spec: ...         # the desired state
```

#### `k8s/configmap.yaml`

```yaml
# Configuration kept outside the image: changing LOG_LEVEL does not require a rebuild.
apiVersion: v1
kind: ConfigMap
metadata:
  name: claims-risk-config
data:
  LOG_LEVEL: "INFO"
  MODEL_VERSION: "0.1.0"
```

Key–value pairs injected as **environment variables** — the same ones used with `docker run -e`. Values are quoted because everything in a ConfigMap is text.

#### `k8s/deployment.yaml`

```yaml
# Deployment = "I want N replicas of this container, and keep them alive".
# Kubernetes continuously compares the desired state (this file) with the actual one.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: claims-risk-service
  labels:
    app: claims-risk-service
spec:
  replicas: 2                          # 2 pods: if one dies, the other keeps serving
  selector:
    matchLabels:
      app: claims-risk-service         # which pods "belong" to this Deployment
  template:
    metadata:
      labels:
        app: claims-risk-service
    spec:
      securityContext:
        runAsNonRoot: true             # Kubernetes refuses to start it if the image runs as root
        runAsUser: 10001
      containers:
        - name: api
          image: claims-risk-service:local
          imagePullPolicy: IfNotPresent  # use the image loaded into kind, do not try to pull it
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: claims-risk-config
          resources:
            requests:                  # what the scheduler RESERVES to place the pod
              cpu: "100m"
              memory: "256Mi"
            limits:                    # ceiling: exceeding the memory limit -> OOMKilled
              cpu: "500m"
              memory: "512Mi"
          livenessProbe:               # if it fails -> restart the container
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:              # if it fails -> remove it from the Service (no restart)
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 3
            periodSeconds: 5
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: tmp
              mountPath: /tmp          # the only writable location
      volumes:
        - name: tmp
          emptyDir: {}
```

- **`replicas: 2`** — if one pod dies, the other keeps serving while Kubernetes replaces the first.
- **`selector` vs. `template`** — `template` is the **mould** for the pods; `template.metadata.labels` is the label each pod gets; `selector.matchLabels` says which pods belong to the Deployment. They **must match** (Kubernetes rejects the manifest otherwise).
- **Pod `securityContext`** — `runAsNonRoot: true` makes Kubernetes **refuse to start** a container that would run as root; UID 10001 is the `appuser` from the Dockerfile. The Dockerfile creates the user, Kubernetes enforces it.
- **`image` + `imagePullPolicy: IfNotPresent`** — use the image already on the node (loaded with `kind load`) instead of pulling from the internet; otherwise: `ImagePullBackOff`. In production the image would be `…dkr.ecr…/claims-risk-service:<commit-sha>`.
- **`envFrom.configMapRef`** — loads **all** ConfigMap keys as environment variables.
- **`resources`** — `100m` = 100 millicores (10 % of a core); `256Mi` = 256 mebibytes.
  - **requests**: what the **scheduler reserves** to place the pod. No node with enough free capacity → `Pending`.
  - **limits**: the **ceiling**. Over the CPU limit → *throttling*; over the memory limit → **`OOMKilled`**.
  - GPUs are requested the same way (`nvidia.com/gpu: 1`), usually on dedicated nodes with taints/tolerations.
- **Probes** — the kubelet calls these endpoints after `initialDelaySeconds`, every `periodSeconds`.
  - **liveness** (`/health`) fails repeatedly → **restart the container**.
  - **readiness** (`/ready`) fails → **removed from the Service** (no traffic), no restart; rejoins once healthy.
- **Container `securityContext`** — `allowPrivilegeEscalation: false`; `readOnlyRootFilesystem: true` (the whole filesystem is read-only: a compromised app cannot modify code or install tools — hence `PYTHONDONTWRITEBYTECODE=1` in the Dockerfile).
- **`emptyDir` on `/tmp`** — a temporary empty directory, the **only writable location**; deleted with the pod.

#### `k8s/service.yaml`

```yaml
# Service = stable IP/DNS name in front of the pods (which are ephemeral and change IPs).
# It load-balances traffic ONLY across the pods that pass the readinessProbe.
apiVersion: v1
kind: Service
metadata:
  name: claims-risk-service
spec:
  type: ClusterIP                      # reachable only from inside the cluster
  selector:
    app: claims-risk-service
  ports:
    - port: 80                         # Service port
      targetPort: 8000                 # container port
```

- `selector` — traffic goes to pods with this label, **and only the ready ones**.
- `port: 80` (Service) → `targetPort: 8000` (container). Inside the cluster other services call `http://claims-risk-service` — **the Service name is its DNS name**.
- **Service types**: `ClusterIP` (default, internal only), `NodePort` (port on every node), `LoadBalancer` (on EKS creates an AWS load balancer). In production: `ClusterIP` + an **Ingress** routing external HTTP traffic by host and path.

### 8.4 Practice

**Exercise 1 — create the cluster**

```bash
kind create cluster --name claims
kubectl cluster-info --context kind-claims
kubectl get nodes                  # claims-control-plane   Ready
docker ps                          # the node IS a Docker container
kubectl config current-context     # always know which cluster you are talking to
```

**Exercise 2 — build and load the image** (from the repo root)

```bash
docker build -t claims-risk-service:local .
kind load docker-image claims-risk-service:local --name claims
```

**Exercise 3 — deploy**

```bash
kubectl apply -f k8s/
kubectl get pods -w                # ContainerCreating → Running, READY 0/1 → 1/1 (Ctrl+C)
kubectl get deployment,replicaset,pods,service,configmap
kubectl describe service claims-risk-service    # "Endpoints": two pod IPs
```

Note the naming hierarchy: Deployment `claims-risk-service` → ReplicaSet `claims-risk-service-7d9f8c…` → pods `claims-risk-service-7d9f8c…-xk2p4`.

| Pod status | Meaning | First check |
|---|---|---|
| `Pending` | No node has enough resources | `kubectl describe pod` → Events |
| `ImagePullBackOff` | Image not found | Did you `kind load`? Does the name match? |
| `CrashLoopBackOff` | Container starts and dies repeatedly | `kubectl logs <pod>` (and `--previous`) |
| `CreateContainerConfigError` | Missing configuration (e.g. the ConfigMap) | `kubectl describe pod` |
| `Running` but `0/1` | Alive but readiness failing | `kubectl describe pod` → Events |

**Exercise 4 — access the service**

```bash
kubectl port-forward service/claims-risk-service 8080:80
```

Open `http://127.0.0.1:8080/docs`. In another terminal:

```bash
kubectl logs -l app=claims-risk-service --prefix -f
```

`-l` selects pods by label; `--prefix` shows which pod each line comes from. All requests hit **one pod**: `port-forward` is a debugging tunnel to a single pod and bypasses the Service's load balancing.

**Exercise 5 — call from inside the cluster (DNS and load balancing)**

```bash
kubectl run curl --rm -it --image=curlimages/curl -- sh
  for i in $(seq 1 10); do curl -s http://claims-risk-service/health; echo; done
  exit
kubectl logs -l app=claims-risk-service --prefix | grep health
```

Requests are now **spread across both pods**, and you used `http://claims-risk-service` — no IP, no port: the cluster's internal **DNS** resolves the Service name. That is how microservices talk to each other.

**Exercise 6 — self-healing and desired state**

```bash
kubectl delete pod <one-pod-name>
kubectl get pods                   # a new pod appears immediately
kubectl scale deployment claims-risk-service --replicas=3
kubectl get pods                   # 3 pods
kubectl apply -f k8s/
kubectl get pods                   # back to 2: the file says replicas: 2
```

A manual change is corrected by re-applying the declared state — the same idea as Terraform drift. That is why in production nobody runs `kubectl scale` by hand: the file changes in Git. This is the essence of **GitOps** (Git is the single source of truth; ArgoCD continuously re-applies it).

**Exercise 7 — a failed deployment that breaks nothing** (the most valuable one)

```bash
kubectl set env deployment/claims-risk-service MODEL_PATH=/does/not/exist
kubectl rollout status deployment/claims-risk-service     # hangs — leave it
```

In another terminal:

```bash
kubectl get pods
kubectl describe pod <new-pod-name>    # Events: Readiness probe failed ... statuscode: 503
```

You see the **2 old pods** `Running 1/1`, still serving, and **1 new pod** `Running 0/1`. What happens:

1. The new pod starts but cannot load the model.
2. `/health` → 200 → liveness passes → **no restart**.
3. `/ready` → 503 → readiness fails → **no traffic**.
4. Kubernetes does **not** stop the old pods until the new one is ready. It never will, so the rollout stalls and **the service keeps running** on the previous version.

**A broken deployment caused zero downtime.** With only a liveness probe, or a health endpoint that also checked the model, the pod would enter a restart loop instead.

Default rolling update settings: `maxSurge` 25 % (rounded up) and `maxUnavailable` 25 % (rounded down). With 2 replicas: 1 extra pod, 0 unavailable — hence 3 pods and no old pod stopped.

Roll back (`Ctrl+C` on `rollout status` first):

```bash
kubectl rollout undo deployment/claims-risk-service
kubectl rollout status deployment/claims-risk-service
kubectl rollout history deployment/claims-risk-service
```

**Exercise 8 — security from the inside**

```bash
kubectl exec -it deployment/claims-risk-service -- sh
  whoami                                   # appuser
  touch /app/test                          # Read-only file system
  touch /tmp/test                          # works: the emptyDir
  env | grep -E "LOG_LEVEL|MODEL_VERSION"  # values from the ConfigMap
  exit
```

In Docker, `touch /app/test` failed on user permissions; here it fails **regardless of permissions** because the filesystem is read-only. Two layers of defence.

**Exercise 9 — the ConfigMap trap**

Change `LOG_LEVEL` to `"WARNING"` in `k8s/configmap.yaml`, then:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl exec deployment/claims-risk-service -- env | grep LOG_LEVEL      # still INFO!
kubectl rollout restart deployment/claims-risk-service
kubectl exec deployment/claims-risk-service -- env | grep LOG_LEVEL      # WARNING
```

Environment variables are read **only at container start**; changing a ConfigMap does not affect running pods. Helm solves this in production by restarting the Deployment when configuration changes. Revert the file to `INFO`.

**Cleanup**

```bash
kind delete cluster --name claims
docker ps            # stop any leftover containers from earlier exercises
```

### 8.5 Interview notes

- **A pod dies — what happens?** The ReplicaSet notices the gap between desired and actual state and creates a new one (control loop, self-healing).
- **Liveness vs. readiness** — restart vs. remove from traffic. Example: a model that fails to load should not restart in a loop; and during a rollout, readiness prevents a broken version from replacing a working one.
- **Zero-downtime deployments** — rolling update + a correct readiness probe; old pods stop only when new ones are ready (`maxSurge`, `maxUnavailable`). If it goes wrong: `kubectl rollout undo`, or revert the commit in GitOps.
- **Requests vs. limits** — scheduler reservation vs. ceiling; memory over limit → `OOMKilled`, CPU over limit → throttling.
- **`CrashLoopBackOff`?** `kubectl logs` (+ `--previous`) and `kubectl describe pod`. `ImagePullBackOff`: image name, tag, registry permissions.
- **Changed a ConfigMap and nothing happened?** Env vars are read at start: `rollout restart`, or let Helm do it.
- **Deployment vs. StatefulSet** — stateless, interchangeable pods (APIs) vs. stable identity and persistent storage per pod (databases, queues).
- **Autoscaling** — **HorizontalPodAutoscaler (HPA)** adds/removes replicas on CPU or custom metrics; utilisation is computed against `requests`.
- **How does an EKS pod access S3 or Bedrock?** **IRSA** (IAM Roles for Service Accounts) or **EKS Pod Identity**: temporary, least-privilege credentials, no stored keys — the **same OIDC principle** as GitLab CI → AWS.
- **Helm** — package manager for Kubernetes: manifests become parametrised templates (*charts*), one values file per environment, versioned releases.
- **Namespaces** — logical partitions inside a cluster, per team or environment, with their own RBAC and resource quotas.

---

## 9. The end-to-end flow

1. **Model** — a scikit-learn model scores claim risk; trained on synthetic data during the image build. In production: a separate training pipeline and a model registry (S3 / SageMaker Model Registry), version via `MODEL_VERSION`.
2. **API** — FastAPI exposes `/predict`, plus what operators need: `/health`, `/ready`, `/metrics`, JSON logs.
3. **Local or container** — run with uvicorn, or packaged in a Docker image (multi-stage, non-root) that behaves identically everywhere.
4. **CI on every push** — GitLab runs `lint → test → build`. Failures stop the pipeline; broken code never becomes an image. Success: the image is tagged with the **commit SHA** and pushed to the registry (GitLab, and ECR via OIDC). Terraform is validated in parallel.
5. **Infrastructure with Terraform** — ECR, S3 and the OIDC role for keyless CI access. In a real setup the same code would create the network and the **EKS cluster**.
6. **Running on Kubernetes** — the Deployment pulls the image and keeps 2 replicas, applying probes, resource limits and the ConfigMap; the Service provides a stable address and balances traffic across ready pods.
7. **CD — next step (not implemented)** — GitOps: the pipeline updates the image tag in a manifest repo / Helm chart; **ArgoCD** syncs the cluster; Kubernetes performs a **rolling update** (new pods start, pass readiness, then old pods receive `SIGTERM` and stop cleanly) → deployments without downtime.
8. **Continuous operation** — Prometheus scrapes `/metrics`, logs are centralised (CloudWatch, Loki), alerts on p95 latency and 5xx rate, and model **drift** monitoring.

| Layer | Tool |
|---|---|
| Packaging | Docker |
| CI/CD | GitLab CI |
| Infrastructure | Terraform or AWS CDK |
| Orchestration | Kubernetes (on AWS: **EKS**) — alternative: ECS |
| Deployment into the cluster | Helm + ArgoCD (GitOps) |
| Observability | Prometheus / Grafana or CloudWatch |

---

## 10. Interview cheat sheet

**One-minute project pitch**

> To prepare for MLOps / AI platform roles I built a small end-to-end project: an AI service that scores insurance-claim risk on synthetic data — deliberately focused on operations rather than modelling. It is a FastAPI application with separate health and readiness endpoints, Prometheus metrics and structured JSON logging, packaged in a multi-stage Docker image running as non-root. A GitLab CI pipeline runs linting and tests, builds the image and pushes it tagged with the commit SHA. The AWS infrastructure — ECR, S3 and an IAM role — is defined in Terraform, and the pipeline authenticates to AWS via OIDC, without static access keys and with least-privilege permissions limited to the main branch. The service runs on Kubernetes with probes, resource limits and a ConfigMap; a failed rollout keeps serving the previous version thanks to the readiness probe.

**The debugging story** (shows real practice): *the pipeline failed in the lint stage — `ruff check` passed locally but `ruff format --check` did not; they are two different checks. Lesson: reproduce locally exactly what the pipeline runs; in a team, pre-commit hooks.*

**Ten one-liners**

1. **Image vs. container** — immutable template vs. running instance.
2. **Multi-stage build** — build tools stay out of the final image: smaller and safer.
3. **Secrets** — never in the image; injected at runtime from a secret manager.
4. **cache vs. artifacts** — speed-up vs. kept results.
5. **OIDC** — signed token per job → temporary credentials; nothing to rotate or leak.
6. **Trust vs. permission policy** — who may assume the role vs. what it may do.
7. **Terraform state** — map code ↔ reality; S3 + encryption + locking; never in git.
8. **plan / apply** — reviewable dry-run on each MR; apply with approval.
9. **Liveness vs. readiness** — restart vs. remove from traffic.
10. **Requests vs. limits** — reservation vs. ceiling (OOMKilled / throttling).

---

## 11. Command cheat sheet

```bash
# ---------- Python ----------
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && ruff format --check .      # what CI runs
ruff check . --fix && ruff format .        # fix
pytest -v | pytest --collect-only
python -m app.train
uvicorn app.main:app --reload              # http://127.0.0.1:8000/docs

# ---------- Docker ----------
docker build -t claims-risk-service:local .
docker run --rm -p 8000:8000 --name claims claims-risk-service:local
docker run --rm -p 8000:8000 -e LOG_LEVEL=WARNING claims-risk-service:local
docker ps | docker logs -f claims | docker exec -it claims sh | docker stop claims
docker images | docker history <image> | docker system df | docker image prune

# ---------- Git / GitLab ----------
git remote add gitlab https://gitlab.com/USER/claims-risk-service.git
git push gitlab main && git push origin main
git fetch gitlab && git log --oneline gitlab/main..main
git commit --allow-empty -m "Trigger CI"
git rm -r --cached <path>                  # untrack without deleting

# ---------- AWS ----------
aws configure
aws sts get-caller-identity

# ---------- Terraform ----------
terraform init | terraform init -reconfigure | terraform init -migrate-state
terraform fmt | terraform validate | terraform console
terraform plan | terraform apply | terraform destroy
terraform output | terraform state list | terraform state show <resource>

# ---------- Kubernetes ----------
kind create cluster --name claims | kind delete cluster --name claims
kind load docker-image claims-risk-service:local --name claims
kubectl config current-context
kubectl apply -f k8s/
kubectl get pods -w | kubectl get deploy,rs,pods,svc,cm
kubectl describe pod <pod> | kubectl logs <pod> [--previous]
kubectl logs -l app=claims-risk-service --prefix -f
kubectl port-forward service/claims-risk-service 8080:80
kubectl exec -it deployment/claims-risk-service -- sh
kubectl scale deployment claims-risk-service --replicas=3
kubectl set env deployment/claims-risk-service KEY=value
kubectl rollout status|undo|history|restart deployment/claims-risk-service
```

---

## 12. Next steps

- **Continuous deployment** — Helm chart + **ArgoCD** (GitOps) on a local kind cluster, then on EKS.
- **Terraform in CI** — `plan` on every MR and `apply` with `when: manual`, authenticated via OIDC with a dedicated role.
- **EKS with Terraform** — the `terraform-aws-modules/eks` module; IRSA / Pod Identity for pod access to S3 or Bedrock.
- **Daemonless image builds** — replace Docker-in-Docker with Kaniko or Buildah.
- **Pre-commit hooks** — ruff and `terraform fmt` on every commit.
- **Autoscaling and alerting** — HPA; Prometheus + Grafana dashboards and alert rules (p95 latency, 5xx rate).
- **Security scanning** — Trivy for images, Checkov/tfsec for Terraform.
- **An LLM endpoint** — add an Amazon Bedrock-backed route and track latency and cost per token.
- **dbt** — a small `dbt-duckdb` project with models and tests, run as an extra CI job.
