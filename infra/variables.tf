variable "aws_region" {
  description = "Región AWS"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Nombre base de los recursos"
  type        = string
  default     = "claims-risk-service"
}

variable "owner" {
  description = "Responsable (se usa en tags para asignar costes)"
  type        = string
  default     = "fernando"
}

variable "gitlab_project_path" {
  description = "Ruta del proyecto en GitLab, p. ej. 'usuario/claims-risk-service'"
  type        = string
}
