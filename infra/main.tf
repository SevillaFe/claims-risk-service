provider "aws" {
  region = var.aws_region

  # Tags en TODOS los recursos: permiten filtrar costes por proyecto en Cost Explorer
  default_tags {
    tags = {
      Project   = var.project_name
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}

# =====================================================================
# 1) ECR: registry privado de imágenes Docker
# =====================================================================
resource "aws_ecr_repository" "app" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE" # un tag (commit SHA) no puede sobrescribirse: trazabilidad
  force_delete         = true        # solo para la demo: permite destroy con imágenes dentro

  image_scanning_configuration {
    scan_on_push = true # escaneo de vulnerabilidades (CVE) en cada push
  }
}

# Control de costes: conservar solo las 10 últimas imágenes
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
# 2) S3: bucket para artefactos de modelos (privado, cifrado, versionado)
# =====================================================================
resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${var.project_name}-artifacts-" # AWS añade un sufijo único
  force_destroy = true                             # solo para la demo
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
    status = "Enabled" # poder volver a una versión anterior del modelo
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
# 3) OIDC: GitLab CI se autentica en AWS SIN access keys
#    GitLab emite un token firmado por job -> AWS lo verifica ->
#    entrega credenciales temporales (1 h) de un rol concreto.
#    Nota: solo puede existir UN provider por URL en la cuenta AWS.
# =====================================================================
data "tls_certificate" "gitlab" {
  url = "https://gitlab.com"
}

resource "aws_iam_openid_connect_provider" "gitlab" {
  url             = "https://gitlab.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.gitlab.certificates[0].sha1_fingerprint]
}

# Trust policy: QUIÉN puede asumir el rol -> solo la rama main de TU proyecto
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

# Permission policy: QUÉ puede hacer el rol -> mínimo privilegio
data "aws_iam_policy_document" "gitlab_ci_permissions" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"] # esta acción no admite restringir por recurso
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
