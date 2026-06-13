# Frequently Asked Questions

Q&A for engineers encountering this stack for the first time, or returning after a gap.

---

## Architecture

**Q: Why is RDS private but the dashboard public?**

A: The ALB and EC2/ECS task are in a *public subnet* — they have internet-routable IPs and
the ALB accepts inbound HTTPS from `0.0.0.0/0`. RDS is in a *private subnet* — it has no
internet route and its security group only allows inbound on port 5432 from the EC2/ECS
security group. The dashboard reaches RDS via VPC-internal routing (private IP), not the
internet. This is the standard "three-tier" pattern: internet → public subnet (app) →
private subnet (data).

---

**Q: Why are there two MLflow experiments (`truck-delay-classification` vs `truck-delay-hp-tuning`)?**

A: Keeping them separate makes the MLflow UI much easier to navigate:

- `truck-delay-classification` (Lab C) — 4 baseline runs: Logistic Regression, Random
  Forest, XGBoost, and one tuned XGBoost run. These are the "official" training runs used
  to produce the registered model.
- `truck-delay-hp-tuning` (Lab D) — ~70 PyCaret/Optuna trials. These are exploratory
  search runs and would flood the baseline experiment if mixed in.

The MLflow Model Registry name (`truck-delay-classifier`) and version number are the
same regardless of which experiment produced the run. Only the `run_id` inside the
registered model points to the originating experiment.

---

**Q: Where do I get the RDS password?**

A: From AWS Secrets Manager — it is never stored in code, config files, or git history.

```bash
aws secretsmanager get-secret-value \
  --secret-id <PROJECT_NAME>/rds-master-password \
  --region <AWS_REGION> \
  --query SecretString \
  --output text
```

Note the separator is a **slash** (`/`), not a hyphen. If you get
`ResourceNotFoundException`, run `aws secretsmanager list-secrets` to find the exact name
(this was Issue §3 in the implementation log).

---

**Q: How do I connect to RDS from my laptop?**

A: RDS is in a private subnet — direct connections from the internet are blocked. Use an
SSH tunnel via the EC2 bastion:

```bash
# Run this in a separate terminal and leave it open:
ssh -i <PROJECT_NAME>-key.pem \
    -L 5432:<RDS_ENDPOINT>:5432 \
    -N ubuntu@<EC2_PUBLIC_IP>
```

Then in your notebook or psql client, connect to `localhost:5432`. See Issue §6 in
`Nakobas-Implementation/03-Issues-and-Fixes.md`.

---

**Q: What if `final_features.csv` schema changes?**

A: Schema drift between the feature engineering output and the prediction pipeline is the
most common source of silent bugs in this stack. When the schema changes:

1. **Regenerate `feature_metadata.json`** — this file is saved alongside `final_features.csv`
   in S3 and records the column names, dtypes, and shape. It is the ground truth for the
   schema at training time.

2. **Update `config.py`** — the following three lists must exactly match the columns in
   the feature matrix that the scaler and encoder were fit on:
   - `CONTINUOUS_FEATURES` — columns passed to `StandardScaler`
   - `CATEGORICAL_FEATURES` — columns passed to `OneHotEncoder`
   - `ENCODE_COLUMNS` — alias used by some utility functions (must be kept in sync)

3. **Retrain and re-register** — if the schema changes, the existing `encoder.pkl` and
   `scaler.pkl` are invalid. Re-run Lab C to produce new artifacts and register a new
   model version.

4. **Update any SQL aliases** — `utils.py`'s `fetch_predictions_data()` SQL query aliases
   column names that must match `config.py`. Drift between the SQL alias and the config
   list was the root cause of Issues §18 and §22.

The safest approach is to add a schema validation step at the start of the prediction
pipeline: load `feature_metadata.json` from S3 and assert that the current input
DataFrame has the same columns and dtypes before calling `predict`.

---

**Q: The CloudFormation stack is in `DELETE_FAILED` state. What do I do?**

A: Most commonly caused by the S3 bucket not being empty (versioning is on — `aws s3 rm
--recursive` only removes current versions). Run the boto3 pagination script in
`Nakobas-Implementation/04-Teardown.md` to delete all object versions and delete markers,
then retry:

```bash
aws cloudformation delete-stack --stack-name m3-stack --region <AWS_REGION>
```

If the stack is still stuck after emptying S3, check CloudFormation Events in the console
for the specific resource causing the failure, manually delete that resource, then retry.

---

**Q: What is the `Zero-Shot` SageMaker notebook instance?**

A: It is a pre-existing notebook instance in the account that is unrelated to the M3
project. It was in `Stopped` state throughout the M3 session and was intentionally left
alone during teardown. Do not delete it unless you are the owner and know what it contains.

---

**Q: Can I run the Streamlit app locally instead of on EC2?**

A: Yes, for development. You still need the SSH tunnel for RDS access (see above), and
you need to set the same environment variables that `_launch_on_ec2.sh` sets:

```bash
# In your local terminal (with SSH tunnel open):
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=mlops_db
export DB_USER=mlops_admin
export DB_PASSWORD=<PASSWORD_FROM_SECRETS_MANAGER>
export S3_BUCKET=<S3_BUCKET>
export DEMO_MODE=false
export MLFLOW_TRACKING_URI=http://<EC2_PUBLIC_IP>:5000

cd labs/M3_Lab_E_Streamlit_Deployment
streamlit run app.py
```

Note: `DEMO_MODE=false` is required — without it, `batch_score.py` and the app fall back
to heuristic predictions and ignore real AWS resources (Issue §15).

---

**Q: How do I check whether the batch scorer actually ran and wrote predictions?**

A: Connect to RDS (via SSH tunnel) and query the `predictions` table:

```sql
SELECT
    scored_at::date AS score_date,
    COUNT(*)        AS records_scored,
    AVG(delay_prob) AS avg_delay_prob
FROM predictions
GROUP BY scored_at::date
ORDER BY score_date DESC
LIMIT 10;
```

If the table is empty or missing today's date, check:
1. Did the cron / scheduled job fire? (`crontab -l` on EC2, or check EventBridge rule)
2. Did it fail silently? (`cat ~/batch.log | tail -50`)
3. Were the env vars set in the cron shell? (Issue §15 — env vars don't auto-inherit)

---

**Q: What is the difference between `DEMO_MODE` and the "heuristic predictions" message?**

A: Two separate fallback triggers, both resulting in the same user-facing message:

| Trigger | Root Cause |
|---------|-----------|
| `DEMO_MODE=true` (or unset) | Env var forces demo mode regardless of AWS connectivity |
| Model artifacts not loadable from S3 | Wrong S3 key paths in `config.py` (Issue §16) or missing packages in the venv (Issue §21) |

Check `config.py` `S3_MODEL_KEY` / `S3_ENCODER_KEY` / `S3_SCALER_KEY` first, then verify
the venv has `xgboost` and `scikit-learn` installed (`pip list | grep xgboost`).
