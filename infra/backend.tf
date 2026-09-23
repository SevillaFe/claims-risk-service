# ------------------------------------------------------------------
# REMOTE STATE (en un equipo real SIEMPRE):
# El state es el "mapa" entre este código y los recursos reales de AWS.
# En local solo sirve para una persona. En equipo va a S3 con locking,
# para que dos pipelines no modifiquen la infraestructura a la vez.
#
# Para la demo usamos state local. Para activarlo, crea el bucket y descomenta:
#
# terraform {
#   backend "s3" {
#     bucket       = "mi-bucket-de-terraform-state"
#     key          = "claims-risk-service/terraform.tfstate"
#     region       = "eu-central-1"
#     encrypt      = true
#     use_lockfile = true   # locking nativo en S3 (Terraform >= 1.10); antes: DynamoDB
#   }
# }
# ------------------------------------------------------------------
