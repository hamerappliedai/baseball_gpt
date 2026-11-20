# Image repositories for the app and ops images (deploy/*.Dockerfile).

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["app", "ops"])
  name                 = "${local.name}/${each.key}"
  image_tag_mutability = "MUTABLE" # `latest` moves; CI (step 5) also pushes a tag per commit
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep the 20 newest images; untagged layers go after a day.
resource "aws_ecr_lifecycle_policy" "repo" {
  for_each   = aws_ecr_repository.repo
  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "drop untagged images after a day"
        selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 1 }
        action       = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "keep the 20 newest images"
        selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
        action       = { type = "expire" }
      },
    ]
  })
}
