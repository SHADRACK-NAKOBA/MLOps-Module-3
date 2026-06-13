# Pre-Production Checklist

Complete every item before standing up this stack in a shared or customer-facing account.

---

## Infrastructure as Code

- [ ] **Review IaC before deploying** — `AWS_setup/m3_setup.yaml` and `AWS_setup/deploy_m3.sh`
      were written for a single-developer learning account. Have a second engineer review
      security groups, IAM policies, and parameter defaults before running in production.
- [ ] **Migrate to org-standard IaC** if the company uses Terraform or CDK instead of
      CloudFormation. Keep the same logical resource set but apply company-standard tagging,
      naming conventions, and module structure.
- [ ] **Parameterise for environments** — add `Environment` (staging / production) as a
      CloudFormation parameter; use it in resource names and tags so staging and production
      can coexist in the same account.

---

## RDS

- [ ] **Enable automated backups** — set `BackupRetentionPeriod` ≥ 7 days in the
      CloudFormation template (current value: check `m3_setup.yaml`).
- [ ] **Enable Multi-AZ** — set `MultiAZ: true` in the `AWS::RDS::DBInstance` resource.
      This provides automatic failover; the current single-AZ setup has no HA.
- [ ] **Review parameter group** — confirm `max_connections`, `work_mem`,
      `shared_buffers` are sized for production query load, not the default micro-instance
      defaults.
- [ ] **Confirm no public access** — RDS is already in a private subnet (correct); verify
      `PubliclyAccessible: false` is set and the security group does not allow internet
      ingress on port 5432.
- [ ] **Rotate the `mlops_admin` password** — enable automatic rotation via a Secrets
      Manager rotation Lambda (the `AWS::SecretsManager::RotationSchedule` resource). The
      current setup writes the password once and never rotates it.
- [ ] **Enable storage encryption** — confirm `StorageEncrypted: true` and a CMK is
      specified (not the default AWS-managed key) if your compliance posture requires it.

---

## MLflow Tracking Server

- [ ] **Move off single EC2** — the current setup runs MLflow as a `nohup` process on
      an EC2 instance. This is a single point of failure and has no TLS. Options:
      - **ECS/Fargate service** behind an ALB — containerize the MLflow server,
        use S3 as artifact store (already in place) and RDS/Aurora as backend store
        (already in place), expose via HTTPS listener on ALB.
      - **Managed MLflow** — Databricks MLflow or Amazon SageMaker Experiments if the
        org is already on one of those platforms.
- [ ] **Restrict MLflow UI access** — currently open to `0.0.0.0/0` on port 5000.
      In production, put it behind the ALB with IAM/Cognito auth or restrict to VPN CIDR.

---

## Streamlit Dashboard

- [ ] **Containerize the app** — this is exactly what Module 4 does. Follow the
      `M4-PROD-Implementation/` guide in that repo. The container should:
      - Read `DB_*` / `S3_*` config from environment variables (not hardcoded).
      - Pull secrets at startup from Secrets Manager via the ECS task role (no static
        access keys).
      - Expose port 8501 to the ALB target group only (no direct internet access).
- [ ] **Deploy via ECS + ALB** — Module 5 covers this. The ALB provides HTTPS
      termination; the ECS service provides autoscaling and rolling deploys.

---

## Networking and Security Groups

- [ ] **Replace `0.0.0.0/0` ingress rules** — the current stack opens several ports
      to the entire internet for convenience. Replace with:
      - ALB SG → restricted to `0.0.0.0/0` on 443 only (public HTTPS)
      - EC2/ECS SG → allows ingress from ALB SG only (SG-to-SG reference)
      - RDS SG → allows ingress from EC2/ECS SG only (no internet access)
      - MLflow SG → allows ingress from ECS task SG and developer VPN CIDR only
- [ ] **Enable VPC Flow Logs** — required for most compliance frameworks; low cost and
      high diagnostic value.

---

## HTTPS / TLS

- [ ] **Request an ACM certificate** for the dashboard domain.
- [ ] **Add HTTPS listener** on the ALB (port 443), redirect HTTP → HTTPS.
- [ ] See Module 5 for the full HTTPS setup pattern.

---

## Secrets Management

- [ ] **No secrets in code or committed `.env` files** — verify with
      `git grep -i password` and `git grep -i secret` on the production branch.
- [ ] **Inject secrets via ECS task environment** — reference the Secrets Manager ARN
      in the ECS task definition's `secrets` block; the ECS agent fetches the value at
      task start. Never pass secrets as plaintext environment variables in the task
      definition.
- [ ] **Enable Secrets Manager rotation** for the RDS password (see RDS section above).

---

## Data Pipeline (Feature Engineering)

- [ ] **Automate `final_features.csv` generation** — currently run manually in a
      notebook (Lab B). In production this should be a scheduled job:
      - EventBridge rule → Lambda or ECS task, or
      - Airflow DAG (Module 6), or
      - AWS Glue job if data volumes grow.
- [ ] **Validate schema** — after each pipeline run, compare the output schema against
      `feature_metadata.json`. Alert and halt if column counts or types change (this is
      the root cause of issues §18 and §22 in the implementation log).

---

## Model Governance

- [ ] **Gate Staging → Production promotion** — do not auto-promote. Require:
      - Evaluation metrics above a documented threshold (e.g. F1 ≥ 0.65 on a held-out
        validation set from production data).
      - A human approval step in the CI/CD pipeline or MLflow Registry UI.
- [ ] **Version policy** — define how many model versions to retain in MLflow Registry
      and how long to keep `Archived` versions (for audit).
- [ ] **Lineage** — confirm each registered model version has a logged `run_id`
      traceable back to the training data and code commit (`mlflow.set_tag('git_commit',
      ...)`).

---

## Observability

- [ ] **Structured logging** — replace `print()` in `batch_score.py` and `utils.py`
      with Python `logging` writing JSON to stdout; ship to CloudWatch Logs via the ECS
      log driver.
- [ ] **CloudWatch alarms** — at minimum:
      - RDS CPU > 80% for 5 min
      - ECS service task count < desired
      - ALB 5xx error rate > 1%
      - Batch scorer Lambda/task failure
- [ ] **On-call runbooks** — write at least: "MLflow UI unreachable", "dashboard shows
      stale model", "batch scorer not writing predictions". See `03-Go-Live-Checklist.md`.

---

## Cost Controls

- [ ] **Per-environment billing alarms** — the learning stack uses a single `<$10`
      alarm. Production needs environment-level and service-level alarms.
- [ ] **RDS scale-to-zero or scheduled stop** — if the staging environment is not
      24/7, use RDS scheduled stop (Aurora Serverless v2 auto-pauses; provisioned RDS
      can be stopped for up to 7 days via the console or Lambda cron).
- [ ] **SageMaker auto-stop** — never leave a notebook instance running overnight.
      Use SageMaker lifecycle configurations to auto-stop after N minutes of inactivity.
