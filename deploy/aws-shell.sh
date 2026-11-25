#!/bin/sh
# Open an interactive shell in a running app task (ECS Exec), for the account
# commands in backend/manage.py. Needs the Session Manager plugin:
#   brew install --cask session-manager-plugin
set -eu
cd "$(dirname "$0")/.."
export AWS_PROFILE="${AWS_PROFILE:-baseball-gpt}"
export AWS_REGION="$(deploy/tf.sh -chdir=infra output -raw region)"
cluster=$(deploy/tf.sh -chdir=infra output -raw ecs_cluster)
task=$(aws ecs list-tasks --cluster "$cluster" --service-name app --desired-status RUNNING --query 'taskArns[0]' --output text)
[ "$task" != "None" ] || { echo "no running app task" >&2; exit 1; }
echo "task ${task##*/}; try: python manage.py user-list"
exec aws ecs execute-command --cluster "$cluster" --task "$task" --container app --interactive --command "/bin/sh"
