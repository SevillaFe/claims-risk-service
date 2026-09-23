# claims-risk-service

AI microservice (claims risk scoring, synthetic data) with the full operations
lifecycle: container, CI/CD, infrastructure as code, Kubernetes and observability.

```
 git push ──► GitLab CI: lint ─► test ─► build ──► GitLab Registry / AWS ECR (OIDC)
                                   └──► terraform validate
                                             │
 Terraform ──► AWS: ECR · S3 (artifacts) · IAM OIDC role (least privilege)
                                             │
 Kubernetes (kind) ◄── image ── Deployment (2 replicas, probes, limits) ─► Service
                                    └── /metrics (Prometheus) · JSON logs (stdout)
```

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m app.train
pytest -v
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

## Docker
```bash
docker build -t claims-risk-service:local .
docker run --rm -p 8000:8000 claims-risk-service:local
```

## Kubernetes (kind)
```bash
kind create cluster --name claims
kind load docker-image claims-risk-service:local --name claims
kubectl apply -f k8s/
kubectl port-forward svc/claims-risk-service 8080:80
```

## Terraform
```bash
cd infra && cp terraform.tfvars.example terraform.tfvars
terraform init && terraform fmt && terraform validate && terraform plan
```

## Design decisions
| Decision | Rationale |
|---|---|
| Multi-stage build, non-root user | Smaller image, reduced attack surface |
| Liveness `/health` vs. readiness `/ready` | Only restart if the process dies; no traffic while the model isn't loaded |
| JSON logs to stdout, Prometheus metrics | Cloud-native standard: queryable in CloudWatch/Loki, dashboards and alerts in Grafana |
| Image tags = commit SHA, ECR IMMUTABLE | Traceability: every image in production maps to an exact commit |
| GitLab OIDC → AWS instead of access keys | Temporary per-job credentials, nothing to rotate or leak |
| Least-privilege IAM, restricted to `main` | An arbitrary branch can't publish to production |
| `default_tags` + ECR lifecycle policy | Cost allocation and control |

## Next steps (production)
- Remote state in S3 with locking; `terraform plan` on every MR and manual `apply` on `main`
- GitOps deployment with Helm + ArgoCD on EKS
- Alerts (p95 latency, 5xx rate) and model drift monitoring
