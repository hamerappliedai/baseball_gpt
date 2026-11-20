#!/bin/sh
# Run Terraform with credentials from your AWS CLI session.
#   deploy/tf.sh -chdir=infra plan      (any terraform arguments)
# Terraform's AWS provider can't read `aws login` sessions yet, so this asks the
# CLI for short-lived keys for the profile (default baseball-gpt) and passes
# them to Terraform in its environment only. Nothing is written to disk.
set -eu
profile="${AWS_PROFILE:-baseball-gpt}"
creds=$(aws configure export-credentials --profile "$profile" --format env) || {
  echo "No AWS session for profile $profile. Run: aws login --region us-east-2 --remote" >&2
  exit 1
}
eval "$creds"
unset AWS_PROFILE
exec terraform "$@"
