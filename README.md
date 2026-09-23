# claims-risk-service

Microservicio de IA (scoring de riesgo de siniestros, datos sintéticos) con el ciclo
de operación completo: contenedor, CI/CD, infraestructura como código, Kubernetes y observability.

```
 git push ──► GitLab CI: lint ─► test ─► build ──► GitLab Registry / AWS ECR (OIDC)
                                   └──► terraform validate
                                             │
 Terraform ──► AWS: ECR · S3 (artefactos) · IAM rol OIDC (mínimo privilegio)
                                             │
 Kubernetes (kind) ◄── imagen ── Deployment (2 réplicas, probes, limits) ─► Service
                                    └── /metrics (Prometheus) · logs JSON (stdout)
```

## Ejecutar en local
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

## Decisiones de diseño
| Decisión | Motivo |
|---|---|
| Multi-stage build, usuario no-root | Imagen pequeña, menos superficie de ataque |
| Liveness `/health` vs. readiness `/ready` | Reiniciar solo si el proceso muere; sin tráfico mientras el modelo no está cargado |
| Logs JSON a stdout, métricas Prometheus | Estándar cloud-native: consultables en CloudWatch/Loki, dashboards y alertas en Grafana |
| Tags de imagen = commit SHA, ECR IMMUTABLE | Trazabilidad: cada imagen en producción apunta a un commit exacto |
| OIDC GitLab → AWS en vez de access keys | Credenciales temporales por job, nada que rotar ni que se pueda filtrar |
| IAM de mínimo privilegio, limitado a `main` | Una rama cualquiera no puede publicar en producción |
| `default_tags` + lifecycle policy en ECR | Asignación y control de costes |

## Próximos pasos (producción)
- Remote state en S3 con locking; `terraform plan` en cada MR y `apply` manual en `main`
- Despliegue GitOps con Helm + ArgoCD sobre EKS
- Alertas (latencia p95, tasa de 5xx) y monitorización de drift del modelo
