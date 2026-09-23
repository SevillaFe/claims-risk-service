output "ecr_repository_url" {
  description = "URL del registry ECR (valor para ECR_REGISTRY sin el nombre del repo)"
  value       = aws_ecr_repository.app.repository_url
}

output "artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "gitlab_ci_role_arn" {
  description = "Valor para la variable AWS_ROLE_ARN en GitLab CI/CD"
  value       = aws_iam_role.gitlab_ci.arn
}
