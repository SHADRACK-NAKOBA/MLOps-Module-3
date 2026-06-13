# Migration Steps: Learning Account → Production

## Prerequisites

- Access to the target production / staging AWS account with appropriate IAM permissions.
- The org's IaC standard decided (CloudFormation kept, or migrated to Terraform/CDK).
- `01-Pre-Production-Checklist.md` fully reviewed and all blocking items resolved.

---

## Step 1 — Copy Repo into the Org

```bash
# Fork or copy this repo into the org's version control system.
# If the org uses GitHub orgs / GitLab groups / Bitbucket projects:
git clone <THIS_REPO_URL> <ORG_REPO_NAME>
cd <ORG_REPO_NAME>
git remote set-url origin <ORG_REPO_URL>
git push origin main
```

**Before pushing**, scrub the repo:

```bash
# Check for any accidentally committed real values
git grep -i 'password'
git grep -i 'secret'
git grep -rE '[0-9]{12}'   # AWS account IDs are 12 digits
git grep -rE 'arn:aws:iam::[0-9]'
ls *.pem 2>/dev/null || echo "no pem files (good)"
```

If any real values are found, remove them, replace with placeholders, and amend or
rebase before pushing. Consider running `git-secrets` or `truffleHog` as a pre-push hook.

---

## Step 2 — Re-Parameterise `AWS_setup/config.yaml`

Update for the target account:

```yaml
project_name: <PROJECT_NAME>       # e.g. freshbasket-m3-staging
aws_region:   <AWS_REGION>         # target account's primary region
alert_email:  <OPS_EMAIL>          # ops/on-call distribution list, not a personal address
billing_alert_threshold_usd: 50    # appropriate for the environment
```

For production, consider adding to the CloudFormation template:

- `Environment` parameter (`staging` / `production`) used in resource names and tags.
- `AllowedCIDR` parameter for ALB / MLflow security group ingress (replaces `0.0.0.0/0`).

---

## Step 3 — Stand Up Infra in `staging` First

```bash
cd AWS_setup
./deploy_m3.sh
```

Run all 4 verification scripts (see `Nakobas-Implementation/02-Step-by-Step.md` §5).
Do not proceed to data/model steps until all show `PASS`.

> **Never deploy directly to production without a staging run.**
> The deploy script creates real AWS resources that incur charges from the moment they
> start. Fix all issues in staging; tear down staging before production deploy.

---

## Step 4 — Re-Run Labs B/C with Production Data Sources

The M3 learning setup loads 7 CSV files from `data/raw/` via `load_csvs.py`. In
production, the source data is likely:

- S3 landing zone (files dropped by FreshBasket's operational systems), or
- A Glue/Athena catalog over the raw S3 data, or
- A direct database connection to the operational PostgreSQL/MySQL.

Replace the CSV load step in Lab B with the appropriate production data source. The
downstream feature engineering code should be identical — only the ingestion step changes.

After Lab B, verify:

```bash
# Shape check
python3 -c "
import pandas as pd
df = pd.read_csv('labs/data/processed/final_features.csv')
print(df.shape)          # expect (N, 37) — N >= 12308 for prod data
print(df.dtypes.value_counts())
"
```

After Lab C, note the new baseline F1 score for use in Lab D.

---

## Step 5 — Re-Run Lab D HP Tuning Against New Baseline

In `labs/M3_Lab_D_MLOps_HP_Tuning.ipynb`, update:

```python
BASELINE_F1 = <NEW_BASELINE_F1>   # from Lab C on production data
```

Run HP tuning on SageMaker. Only register a new model version if it beats the baseline.
Delete the SageMaker notebook instance immediately after (it incurs charges per hour even
when idle).

---

## Step 6 — Containerize Lab E (→ Module 4)

Follow the Module 4 repo's `PROD-Implementation/02-Migration-Steps.md` to:

1. Add a `Dockerfile` to `labs/M3_Lab_E_Streamlit_Deployment/`.
2. Build and push the image to ECR:
   ```bash
   aws ecr get-login-password --region <AWS_REGION> | \
     docker login --username AWS \
     --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com

   docker build -t <PROJECT_NAME>-dashboard .
   docker tag <PROJECT_NAME>-dashboard:latest \
     <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<PROJECT_NAME>-dashboard:latest
   docker push \
     <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<PROJECT_NAME>-dashboard:latest
   ```
3. Write an ECS task definition referencing the ECR image.
4. Confirm the container reads all config from environment variables injected by the
   ECS task definition's `secrets` block (no hardcoded values).

---

## Step 7 — Deploy via ECS + ALB (→ Module 5)

Follow the Module 5 repo to:

1. Create an ECS cluster and service for the dashboard container.
2. Attach an ALB with HTTPS listener (ACM cert required).
3. Set the ECS service's `desiredCount` ≥ 2 for HA.
4. Configure ECS service autoscaling based on ALB request count or ECS CPU.
5. Add health check: ALB checks `/health` or `/_stcore/health` (Streamlit built-in).

---

## Step 8 — Replace Cron with a Real Scheduler

The learning setup runs `batch_score.py` via crontab on EC2. Replace with:

- **EventBridge Scheduler** → ECS `RunTask` (simplest; no extra infrastructure)
- **Airflow DAG** (Module 6) — use if data pipeline orchestration is needed alongside
  batch scoring
- **Lambda** (if `batch_score.py` can be made stateless and runs in < 15 min)

Ensure idempotency: re-running the batch scorer on the same day should not insert
duplicate rows into the `predictions` table. The current `LEFT JOIN ... WHERE p.truck_id
IS NULL` logic provides this; verify it holds at production data volume before scheduling.

---

## Step 9 — Cut Over DNS and Promote Model to `Production`

```bash
# Promote the model in MLflow Registry from Staging to Production
# (do this ONLY after go-live checklist is complete — see 03-Go-Live-Checklist.md)
python3 - <<'EOF'
import mlflow
client = mlflow.tracking.MlflowClient(tracking_uri='http://<EC2_PUBLIC_IP>:5000')
client.transition_model_version_stage(
    name='truck-delay-classifier',
    version=1,                        # or current highest version
    stage='Production'
)
print('Model promoted to Production.')
EOF
```

Update DNS (Route 53 or company DNS) to point the dashboard domain to the new ALB.

---

## Step 10 — Decommission the Learning-Account Resources

Once production is verified, tear down the learning stack:

```bash
# Follow Nakobas-Implementation/04-Teardown.md exactly.
# Empty S3 bucket first (boto3 pagination script), then:
aws cloudformation delete-stack --stack-name m3-stack --region <AWS_REGION>
```

Do not skip teardown — the learning account is billed for every running resource.
