# Plan: deploy to AWS (milestone 6)

Status: steps 1–3 done; the site is live. Decisions (2026-11-17, region changed 2026-11-20):

- **Infrastructure as code:** Terraform.
- **Region:** `us-east-2` (Ohio). The organization's region policy (an SCP on the
  root) allows workloads only there; `us-west-2` was the first choice but the policy
  blocks EC2, RDS, ECS and S3 in it. CloudFront's certificate and WAF must live in
  `us-east-1`, which the policy allows for those global services.
- **Account:** a dedicated member account, `baseball-gpt`, in the HamerAppliedAI
  organization. The CLI reaches it through the profile `baseball-gpt`, which steps
  from your `aws login` session (Management account) into the account's
  `OrganizationAccountAccessRole`.
- **Domain:** `baseballgpt.hamerappliedai.com`. `hamerappliedai.com` is registered at
  Squarespace and its DNS stays there; you add the records by hand (Terraform prints
  them).
- **Shape:** production-style. Two app containers in two availability zones, private
  subnets, a multi-AZ database. The estimated cost is accepted.

Nothing here is built until you approve the plan, and nothing that costs money is created
until you approve `terraform apply`.

## What it looks like

```
 visitor ──HTTPS──> CloudFront (baseballgpt.hamerappliedai.com, cert in us-east-1, WAF)
                        │  /assets/*, /api/meta, /api/leaderboard, ... cached
                        │  /api/auth/*, /api/chat: not cached, cookies forwarded
                        ▼
                    ALB (HTTPS, cert in us-east-2; only accepts CloudFront)
                        │
              ┌─────────┴─────────┐        private app subnets (2 AZs)
         ECS Fargate task    ECS Fargate task   FastAPI + built Vue app + embedding model
              └─────────┬─────────┘        outbound via NAT (Claude API)
                        ▼
              RDS PostgreSQL 17 + pgvector, multi-AZ     isolated DB subnets
```

## Components

### Network
- A VPC with three subnet tiers in two availability zones: public (ALB, NAT gateways),
  private (app tasks) and isolated (database, no internet route).
- One NAT gateway per zone, so outbound calls to the Claude API survive losing a zone.
  To save about $35 a month, run one shared NAT instead (a variable).
- Security groups: the ALB accepts HTTPS only from CloudFront's managed prefix list; the
  tasks accept only the ALB; the database accepts only the tasks and the one-off task.

### Database: RDS
- PostgreSQL 17, `db.t4g.small`, multi-AZ, 20 GB gp3 storage (the warehouse is about
  350 MB), encrypted, 7-day automated backups, deletion protection on.
- The master password is managed by RDS in Secrets Manager. It's used only by the one-off
  task (pipeline, dbt, roles, migrations), never by the web app.
- The app connects as `bgpt_reader` and `bgpt_app` as today, with their passwords in
  Secrets Manager.
- Postgres init scripts don't run on RDS, so the extensions and schemas live in
  `db/bootstrap.sql`. Docker Compose mounts it for local volumes; the ops image runs it
  first on RDS. It's idempotent.

### App: ECS Fargate
- One image, built from a new `Dockerfile`:
  - stage 1 builds the Vue app;
  - stage 2 is Python with the backend, plus the embedding model baked in, so tasks
    never download it from Hugging Face at start-up;
  - it uses CPU-only `torch` to keep the image smaller.
- 2 tasks of 1 vCPU and 2 GB, auto-scaling to 4 on CPU.
- **Visitor addresses:** behind CloudFront and the load balancer, the connecting
  address is a CloudFront server, and `--proxy-headers` can't tell which address in the
  chain is the visitor's. So CloudFront forwards `CloudFront-Viewer-Address`, and the app
  reads it (`CLIENT_IP_HEADER`). That header is trustworthy only because nothing but our
  CloudFront distribution can reach the load balancer:
  - its security group allows only CloudFront's address range;
  - its listener rejects requests that lack a secret header CloudFront adds.
- Rolling deploys with a health check on `/api/health`, and circuit-breaker rollback.
- `CLAUDE_MODEL=claude-sonnet-5-5` and other settings come from Terraform variables. The
  Anthropic key and database passwords come from Secrets Manager.

### One-off task ("ops")
- A second image with the pipeline, dbt, `psql` and the same model. It runs on demand
  with `make aws-task CMD=...`.
- **First load:** bootstrap, roles, migrate, then the full pipeline (download from SABR's
  Box, verify, load, dbt, embed) straight into RDS. It's reproducible, needs no laptop,
  and repeats when the 2026 season is released.
- **Every deploy:** `migrate` runs before the new app tasks start.
- **Admin:** `manage.py user-add` and the other account commands.

### Edge: CloudFront and WAF
- CloudFront serves `baseballgpt.hamerappliedai.com` over HTTPS:
  - it caches the static assets and the browse API, which already sends
    `Cache-Control: max-age=3600`;
  - it passes `/api/auth/*` and `/api/chat` straight through, with cookies and no caching;
  - streaming (server-sent events) works through it.
- AWS WAF on CloudFront:
  - managed common rules;
  - a rate rule on `/api/auth/login` and `/api/chat`, a first line of defence before the
    app's own limits.

### Secrets and settings
- Secrets Manager holds:
  - the Anthropic API key (you paste it in once with the AWS CLI; it never goes in
    Terraform state or Git);
  - the `bgpt_reader` and `bgpt_app` passwords (generated by Terraform);
  - the RDS master secret.
- Set a monthly spend limit on the Anthropic key in the Anthropic Console as well.

### Observability and cost guardrails
- CloudWatch logs for the tasks (30 days).
- Alarms emailed to you:
  - 5xx errors;
  - unhealthy tasks;
  - database CPU and free storage;
  - an AWS Budgets alert at a monthly amount you choose.

### Terraform layout
- `infra/bootstrap/`: an S3 bucket for Terraform state, with versioning and native S3
  locking. It's applied once.
- `infra/`: everything else, in a few files (network, database, app, edge, monitoring)
  with a `terraform.tfvars` for the domain, alarm email and sizes.
- Outputs: the DNS records to add at Squarespace and the commands for the one-off tasks.

### DNS at Squarespace

Only the `baseballgpt` subdomain changes; `hamerappliedai.com` itself and its other
records are untouched. You add, in Squarespace's DNS settings (Domains → DNS → Custom records) for `hamerappliedai.com`:

1. **Certificate validation:** two CNAME records, one for each certificate. One is the
   CloudFront certificate for `baseballgpt.hamerappliedai.com`. The other is the load
   balancer's certificate for `origin.baseballgpt.hamerappliedai.com`, the address
   CloudFront uses to reach the load balancer. They look like
   `_abc123.baseballgpt` → `_xyz.acm-validations.aws`. Leave them in place, so the
   certificates renew automatically.
2. **The site:**
   - a CNAME `baseballgpt` → the CloudFront address (`dxxxx.cloudfront.net`);
   - a CNAME `origin.baseballgpt` → the load balancer's address.

Squarespace allows a CNAME on a subdomain, so no DNS move is needed. Validation usually
takes a few minutes after the records are saved.

### Continuous deployment (last step)
- A GitHub Actions workflow on pushes to `main`:
  1. build both images;
  2. push them to ECR;
  3. run `migrate`;
  4. update the service.
- It signs in to AWS with GitHub's OIDC, so no AWS keys are stored in GitHub. The role
  can only be assumed from this repo's `main` branch, which matters because the repo is
  public.

## Estimated monthly cost (us-east-2)

Rough list prices, before free tier, not counting Claude API usage:

| Item | Estimate |
|---|---|
| NAT gateways (2) | $65–70 |
| Fargate, 2 tasks × 1 vCPU / 2 GB | $70–75 |
| RDS `db.t4g.small` multi-AZ + 20 GB storage | $55–60 |
| Application Load Balancer | $20–25 |
| WAF (web ACL + 3–4 rules + requests) | $8–10 |
| CloudFront, Secrets Manager, CloudWatch, ECR, S3 | $5–15 |
| **Total** | **about $220–250 a month** |

You've accepted this. If you want to trim it later:
- one shared NAT gateway: −$35;
- `db.t4g.micro`: −$25, though tight with the search index;
- one task outside busy times.

All of these are variables.

## Steps (each its own PR)

1. **Container images (done):**
   - `deploy/app.Dockerfile` and `deploy/ops.Dockerfile` + `deploy/ops.sh`;
   - `db/bootstrap.sql`;
   - `CLIENT_IP_HEADER` for visitor addresses behind CloudFront;
   - a local `docker compose` profile (`make image-run`) that runs the app image against
     the local database;
   - `ops first-load` tested against an empty Postgres container, standing in for a new
     RDS database.
2. **Terraform foundation (done):** state bucket, network, ECR, Secrets Manager, RDS, the
   ECS cluster and the ops task. Applied in `us-east-2`; images pushed; `first-load` ran
   on Fargate (139 dbt tests pass, 46,487 aliases embedded). See "Running Terraform"
   below.
3. **App and edge (done):** ECS service, ALB, certificates, CloudFront, WAF. Applied in
   two passes around the Squarespace records (see "Step 3: going live"). Live at
   https://baseballgpt.hamerappliedai.com: HTTPS, browse data, search, CloudFront
   caching, security headers, 401 for Ask AI when signed out, and no direct access to
   the load balancer, all checked from the internet.
4. **Monitoring:** alarms and budget.
5. **CI/CD:** the GitHub Actions deploy on merge to `main`.

## Running Terraform

Terraform's AWS provider can't read `aws login` sessions yet, so every Terraform command
goes through `deploy/tf.sh`. It asks the AWS CLI for short-lived keys for the
`baseball-gpt` profile and passes them to Terraform's environment only. Both stacks also
set `allowed_account_ids`, so Terraform refuses to touch any other account.

The account ID is kept out of this public repo: it lives in the git-ignored
`terraform.tfvars` files and `infra/backend.hcl` (see the `.example` files).

```bash
aws login --region us-east-2 --remote        # sign in to the Management account

# once: the state bucket
deploy/tf.sh -chdir=infra/bootstrap init
deploy/tf.sh -chdir=infra/bootstrap apply
deploy/tf.sh -chdir=infra/bootstrap output -raw backend_config > infra/backend.hcl

# the main stack
deploy/tf.sh -chdir=infra init -backend-config=backend.hcl
deploy/tf.sh -chdir=infra plan -out=infra.tfplan
deploy/tf.sh -chdir=infra apply infra.tfplan

# images and the first data load
make aws-push
make aws-task CMD=first-load
```

## Step 3: going live

The certificates must be validated through Squarespace before the load balancer and
CloudFront can use them, so step 3 is applied in two passes.

1. **The Anthropic key.** The app tasks can't start until the secret has a value. Put it
   in without it appearing on screen or in your shell history (zsh):

   ```bash
   read -rs "KEY?Anthropic API key: " && printf %s "$KEY" | aws secretsmanager put-secret-value --profile baseball-gpt --secret-id baseball-gpt/anthropic-api-key --secret-string file:///dev/stdin --query VersionId && unset KEY
   ```

2. **The certificates only:**

   ```bash
   deploy/tf.sh -chdir=infra apply -target=aws_acm_certificate.site -target=aws_acm_certificate.origin
   deploy/tf.sh -chdir=infra output dns_records_validation
   ```

3. **Squarespace, validation records:** add the two CNAMEs it prints (Host and Data exactly
   as shown). Leave them in place; ACM uses them to renew.
4. **Everything else:** `deploy/tf.sh -chdir=infra apply`. It waits for ACM to see the
   records, then creates the load balancer, the app service, WAF and CloudFront
   (CloudFront takes 5–15 minutes).
5. **Squarespace, site records:** `deploy/tf.sh -chdir=infra output dns_records_site` prints
   two more CNAMEs: `baseballgpt` → CloudFront and `origin.baseballgpt` → the load
   balancer.
6. **Your account:** sign-up is closed, so create your Ask AI account in the production
   database from a shell in a running app task (ECS Exec; needs the Session Manager
   plugin, `brew install --cask session-manager-plugin`):

   ```bash
   make aws-shell
   python manage.py user-add --email you@example.com --name "Your Name" --admin
   ```

## What I need from you

- **AWS access on this machine (done):**
  - the AWS CLI and Terraform (`brew install awscli` and
    `brew install hashicorp/tap/terraform`);
  - `aws login`, plus the `baseball-gpt` profile in `~/.aws/config`;
  - I don't handle AWS credentials.
- **DNS:** access to Squarespace's DNS settings (Domains → DNS → Custom records) for `hamerappliedai.com`, to add four CNAME
  records during step 3.
- **Alarm email address,** and a monthly AWS budget figure for the alert.
- **Anthropic key:** paste it into Secrets Manager yourself when step 2 asks. Consider a
  separate key for production, with its own spend limit.
- **Approval** before each `terraform apply`, since that's when money starts being spent.
