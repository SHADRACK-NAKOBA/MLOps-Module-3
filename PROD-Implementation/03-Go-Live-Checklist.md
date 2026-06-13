# Go-Live Checklist

Complete this checklist in a staging environment first. Sign off on each item before
cutting over DNS or promoting the MLflow model to `Production` stage.

---

## Secrets and Credentials

- [ ] `git grep -i password` on the production branch returns zero results
- [ ] `git grep -i secret` on the production branch returns zero results
- [ ] `git grep -rE '[0-9]{12}'` (AWS account ID pattern) returns zero results
- [ ] No `.pem`, `.env`, or `*.secret` files tracked in git
      (`git ls-files | grep -E '\.pem|\.env|\.secret'` — expect empty)
- [ ] All secrets sourced from Secrets Manager / Parameter Store at runtime; none
      hardcoded in ECS task definition or container image
- [ ] Secrets Manager rotation enabled for the RDS password
- [ ] IAM roles follow least privilege; no `AdministratorAccess` attached to any
      service role in production

---

## Infrastructure

- [ ] CloudFormation stack deployed cleanly in the staging account with zero drift
      (`aws cloudformation detect-stack-drift --stack-name <STACK_NAME>`)
- [ ] All 4 verification scripts (`verify_ec2.py`, `verify_s3.py`, `verify_mlflow.py`,
      `verify_rds.py`) show `PASS`
- [ ] Security groups reviewed: no `0.0.0.0/0` on application ports; ingress locked
      to ALB SG or approved CIDR ranges
- [ ] VPC Flow Logs enabled
- [ ] RDS Multi-AZ enabled
- [ ] RDS automated backups enabled with retention ≥ 7 days

---

## HTTPS and Dashboard Availability

- [ ] Dashboard reachable only via HTTPS (`https://<DOMAIN>`)
- [ ] HTTP → HTTPS redirect in place on ALB
- [ ] Direct task port (8501) NOT reachable from the internet
      (`curl http://<EC2_PUBLIC_IP>:8501` should time out or be refused)
- [ ] ACM certificate not expired (`aws acm describe-certificate --certificate-arn <ARN>`)
- [ ] ALB health check returning healthy for all targets
- [ ] Streamlit "By Date / By Truck / By Route" tabs all load real data (not heuristics)
- [ ] Dashboard header shows correct model version and MLflow experiment name

---

## Database

- [ ] `truck_schedule_with_features` table exists and has the expected row count
      (`SELECT COUNT(*) FROM truck_schedule_with_features;` — expect ≥ 12,308)
- [ ] `predictions` table exists (even if empty — avoids the `relation does not exist`
      error on the first batch scorer run)
- [ ] RDS test restore completed successfully from an automated backup
- [ ] Connection to RDS from the app layer is via the ECS task SG only (verified in
      RDS SG inbound rules)

---

## Batch Scorer

- [ ] Batch scorer runs successfully end-to-end in staging with production-scale data
- [ ] Idempotency verified: running the scorer twice on the same date does not insert
      duplicate rows (`SELECT COUNT(*) FROM predictions WHERE scored_at::date = CURRENT_DATE`
      should be the same before and after a re-run)
- [ ] Scheduled job (EventBridge / Airflow) fires correctly in staging
- [ ] Failure alerting configured — if the scorer job fails, CloudWatch alarm or
      Airflow alert fires within 5 minutes

---

## Model

- [ ] Model registered in MLflow Registry as `truck-delay-classifier`; stage is
      `Staging` in staging environment, `Production` in production (post-cutover)
- [ ] Model performance on production holdout set meets baseline threshold
      (F1 ≥ `<AGREED_THRESHOLD>` — document this value in the PR description)
- [ ] Model version lineage traceable: `run_id` → `git_commit` → training data S3 path
- [ ] Human sign-off obtained before `transition_model_version_stage` to `Production`

---

## Observability

- [ ] CloudWatch alarms active:
  - [ ] RDS CPU > 80% for 5 min
  - [ ] ECS service task count < desired count
  - [ ] ALB HTTP 5xx rate > 1% for 5 min
  - [ ] Batch scorer job failure
  - [ ] Production account estimated charges > `<THRESHOLD_USD>`
- [ ] Alarm actions route to the on-call SNS topic (not a personal email)
- [ ] Logs flowing to CloudWatch Logs from ECS tasks and batch scorer
- [ ] Log retention policy set (e.g. 30 days) — infinite retention incurs ongoing cost

---

## Runbooks (Must Exist Before Go-Live)

- [ ] **"MLflow UI unreachable"** — steps to restart the ECS service or fail over;
      how to verify the artifact store (S3) and backend store (RDS) are accessible
- [ ] **"Dashboard shows stale model / heuristic predictions"** — how to verify the
      model artifacts are present in S3 at the correct keys; how to check the ECS task's
      `MLFLOW_TRACKING_URI` and S3 env vars are set correctly
- [ ] **"Batch scorer not writing predictions"** — how to check the scheduler fired;
      how to re-run manually; how to verify idempotency before re-running
- [ ] **"RDS connection refused"** — how to verify the RDS SG allows the ECS task SG;
      how to check RDS status in the console; how to restart without data loss
- [ ] Runbooks stored in the team's wiki / incident management tool, not just this repo

---

## Go/No-Go Decision

| Owner | Sign-off | Date |
|-------|---------|------|
| ML Engineer | | |
| Platform / Infra | | |
| Security | | |
| Product / Business | | |

**Proceed to production cutover only when all checklist items are checked and all
sign-offs are obtained.**
