#!/bin/sh
# Run the ops image once on ECS Fargate and wait for it to finish.
#   deploy/aws-task.sh first-load | migrate | refresh-data | roles | ...
# (the commands are in deploy/ops.sh). Prints the task's log and exits with
# the container's exit code.
set -eu
cd "$(dirname "$0")/.."

cmd="${1:?usage: deploy/aws-task.sh <ops command>, e.g. first-load}"
export AWS_PROFILE="${AWS_PROFILE:-baseball-gpt}"
out() { deploy/tf.sh -chdir=infra output -raw "$1"; }
export AWS_REGION="$(out region)"
cluster=$(out ecs_cluster)
taskdef=$(out ops_task_definition)
log_group=$(out ops_log_group)
subnets=$(deploy/tf.sh -chdir=infra output -json private_subnet_ids | python3 -c "import json,sys; print(','.join(json.load(sys.stdin)))")
sg=$(out ops_security_group_id)

task_arn=$(aws ecs run-task --cluster "$cluster" --task-definition "$taskdef" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$sg],assignPublicIp=DISABLED}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"ops\",\"command\":[\"$cmd\"]}]}" \
  --query 'tasks[0].taskArn' --output text)
task_id=${task_arn##*/}
echo "started $cmd: task $task_id"
echo "follow along in another terminal:"
echo "  aws logs tail $log_group --log-stream-names ops/ops/$task_id --follow --profile $AWS_PROFILE"

last=""
while :; do
  status=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" --query 'tasks[0].lastStatus' --output text)
  if [ "$status" != "$last" ]; then echo "  $(date +%H:%M:%S) $status"; last=$status; fi
  [ "$status" = "STOPPED" ] && break
  sleep 15
done

echo; echo "---- log ----"
aws logs get-log-events --log-group-name "$log_group" --log-stream-name "ops/ops/$task_id" \
  --start-from-head --query 'events[].message' --output text | tr '\t' '\n' || true
echo "-------------"

code=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" --query 'tasks[0].containers[0].exitCode' --output text)
reason=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" --query 'tasks[0].stoppedReason' --output text)
echo "exit code: $code ($reason)"
[ "$code" = "0" ]
