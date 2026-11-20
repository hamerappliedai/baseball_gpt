#!/bin/sh
# Build the production images for arm64 and push them to ECR.
#   deploy/aws-push.sh [app|ops ...]     (default: both)
# Tags: latest, plus the current commit's short hash.
set -eu
cd "$(dirname "$0")/.."

export AWS_PROFILE="${AWS_PROFILE:-baseball-gpt}"
out() { deploy/tf.sh -chdir=infra output -raw "$1"; }
region=$(out region)
registry=$(out ecr_registry)
tag=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain)" ]; then tag="$tag-dirty"; fi

aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry"

images="${*:-app ops}"
for image in $images; do
  repo=$(deploy/tf.sh -chdir=infra output -json ecr_repositories | python3 -c "import json,sys; print(json.load(sys.stdin)['$image'])")
  echo "==> $image -> $repo:$tag"
  docker build --platform linux/arm64 -f "deploy/$image.Dockerfile" -t "$repo:$tag" -t "$repo:latest" .
  docker push "$repo:$tag"
  docker push "$repo:latest"
done
