# Issues and Fixes

Every problem hit during the M3 session, documented for future runs.
Each entry follows: **Symptom / Cause / Fix / Command**.

---

### §1 — `BillingAlertThresholdUsd must be a number` (CloudFormation ValidationError)

**Symptom:** `./deploy_m3.sh` fails at the CloudFormation step with:

```
ValidationError: Parameter 'BillingAlertThresholdUsd' must be a number
```

**Cause:** `config.yaml` stores `billing_alert_threshold_usd: 10`, and the deploy script
reads it as a YAML string. When passed as `"10"` (quoted) to CloudFormation, it fails type
validation for a `Number` parameter.

**Fix:** In `deploy_m3.sh` around line 282, hardcode the value as a bare integer instead
of reading it from the YAML variable:

```bash
# Before (broken):
BillingAlertThresholdUsd="${CFG_BILLING_ALERT_THRESHOLD_USD:-10}"

# After (fixed):
BillingAlertThresholdUsd=10
```

**Command:** `grep -n "BillingAlertThresholdUsd" AWS_setup/deploy_m3.sh` to find the exact line.

---

### §2 — Region Typo in `secretsmanager get-secret-value`

**Symptom:**

```
Could not connect to the endpoint URL: "https://secretsmanager.us-easet-1.amazonaws.com/"
```

**Cause:** Typo — `us-easet-1` instead of `us-east-1`.

**Fix:** Correct the spelling in the `--region` flag.

```bash
# Wrong:
aws secretsmanager get-secret-value --region us-easet-1 ...

# Right:
aws secretsmanager get-secret-value --region us-east-1 ...
```

---

### §3 — Wrong Secret Name (`ResourceNotFoundException`)

**Symptom:**

```
An error occurred (ResourceNotFoundException) when calling the GetSecretValue operation:
Secrets Manager can't find the specified secret.
```

**Cause:** Guessed the secret ID incorrectly (e.g. `<PROJECT_NAME>-rds-master-password`
with a hyphen instead of a slash).

**Fix:** Look up the actual secret name:

```bash
aws secretsmanager list-secrets --region <AWS_REGION> \
  --query "SecretList[*].Name" --output table
```

The actual secret ID is `<PROJECT_NAME>/rds-master-password` (slash separator).

```bash
aws secretsmanager get-secret-value \
  --secret-id <PROJECT_NAME>/rds-master-password \
  --region <AWS_REGION> \
  --query SecretString --output text
```

---

### §4 — `.ipynb` Opens as Raw JSON/Markdown in VS Code

**Symptom:** Opening a `.ipynb` file in VS Code shows raw JSON or an unstyled markdown
view instead of the interactive notebook interface.

**Cause:** The **Jupyter** and **Python** extensions (Microsoft) were not installed.

**Fix:** Extensions panel (`Ctrl+Shift+X`) → search "Jupyter" → install
`ms-toolsai.jupyter`. Also install `ms-python.python` if not present. Reopen the notebook.
VS Code will prompt to select a kernel — choose the local Python 3.10+ interpreter.

---

### §5 — DB_CONFIG Cell Connects to Wrong/Stale Host

**Symptom:** Notebook connects to an old RDS endpoint
(e.g. `mlops-m3-batch-2026...ap-south-1.rds.amazonaws.com`) from a previous session
instead of the current stack's endpoint.

**Cause:** A duplicate / template `DB_CONFIG` cell lower in the notebook was run after
the correct cell. Its stale value overwrote the variable in the kernel's memory.

**Fix:** Always run cells strictly top-to-bottom. If you suspect stale state:
`Ctrl+Shift+P` → "Jupyter: Restart Kernel and Clear Outputs" → re-run from cell 1.

> The Restart icon may not be visible in the notebook toolbar depending on VS Code version;
> use the Command Palette instead.

---

### §6 — `psycopg2.OperationalError: Connection timed out` (Laptop → RDS)

**Symptom:** Running Lab B from your laptop results in:

```
psycopg2.OperationalError: could not connect to server: Connection timed out
```

**Cause:** RDS is in a private subnet with a security group that only allows inbound port
5432 from within the VPC. Direct connections from your laptop are blocked by design.

**Fix:** Open an SSH tunnel in a separate terminal and leave it running throughout the lab:

```bash
ssh -i <PROJECT_NAME>-key.pem \
    -L 5432:<RDS_ENDPOINT>:5432 \
    -N ubuntu@<EC2_PUBLIC_IP>
```

In the notebook, set:

```python
DB_HOST = 'localhost'   # traffic goes through the tunnel
DB_PORT = 5432
```

---

### §7 — SageMaker Terminal: `cd MLOPS-Module-3: No such file or directory`

**Symptom:** After cloning the repo in the SageMaker JupyterLab terminal, `cd MLOPS-Module-3`
fails.

**Cause:** Linux file systems are case-sensitive. The repo clones as `MLOps-Module-3`
(mixed case), not `MLOPS-Module-3`.

**Fix:**

```bash
ls   # see exact folder name
cd MLOps-Module-3
```

---

### §8 — `ModuleNotFoundError: No module named 'seaborn'` on SageMaker (Lab D)

**Symptom:** Lab D notebook fails on import with `ModuleNotFoundError: No module named 'seaborn'`
(or similar for `matplotlib`, `pandas`, etc.).

**Cause:** The SageMaker base conda environment does not include all packages needed by Lab D.

**Fix:** Add a pip install cell before the imports cell and run it first:

```python
!pip install -q seaborn matplotlib pandas numpy boto3 joblib mlflow scikit-learn xgboost
!pip install -q pycaret==3.3.2 optuna
```

---

### §9 — PyCaret `compare_models()` → `ValueError: _CURRENT_EXPERIMENT global variable is not set`

**Symptom:**

```python
ValueError: _CURRENT_EXPERIMENT global variable is not set. Please run setup() first.
```

**Cause:** `setup()` did not actually complete successfully (kernel was interrupted, cell
was skipped, or cells were run out of order), so PyCaret's internal state was never
initialised.

**Fix:** Re-run the `setup()` cell completely. Confirm it finishes without error before
running `compare_models()`.

---

### §10 — PyCaret `setup()` → `Exception: Run with UUID ... is already active`

**Symptom:**

```
Exception: Run with UUID <uuid> is already active. To start a new run, first end the
current run with mlflow.end_run().
```

**Cause:** A previous `setup()` call (from a failed attempt) left an MLflow run open.
Re-running `setup()` tries to start a new run but finds an existing active one.

**Fix:** Add a cell before `setup()` to close any open runs:

```python
import mlflow
# End any orphaned active run
while mlflow.active_run():
    mlflow.end_run()
```

Then re-run `setup()`.

---

### §11 — EC2: `pip install` → `error: externally-managed-environment` (Ubuntu 24.04)

**Symptom:**

```
error: externally-managed-environment
× This environment is externally managed
```

**Cause:** Ubuntu 24.04 enforces PEP 668, which prevents system-wide pip installs outside
a virtual environment.

**Fix:** For a dedicated, single-purpose EC2 instance (like this one), the flag is safe:

```bash
pip install -r requirements.txt --break-system-packages
```

> For production: use a proper `venv` instead of this flag.

---

### §12 — `_launch_on_ec2.sh` → `/usr/bin/env: 'bash\r': No such file or directory`

**Symptom:** Running `./_launch_on_ec2.sh` on EC2 fails immediately:

```
/usr/bin/env: 'bash\r': No such file or directory
```

**Cause:** The script has Windows CRLF (`\r\n`) line endings from being edited on Windows.
Linux interprets `\r` as part of the interpreter name.

**Fix:**

```bash
sed -i 's/\r$//' _launch_on_ec2.sh
# Also fix any other .sh files in the directory:
sed -i 's/\r$//' *.sh
```

---

### §13 — `_launch_on_ec2.sh` → `streamlit: No such file or directory` (venv missing)

**Symptom:** The launch script starts but immediately fails:

```
/home/ubuntu/streamlit-venv/bin/streamlit: No such file or directory
```

**Cause:** The script assumes a Python virtual environment at `/home/ubuntu/streamlit-venv/`
that does not exist yet.

**Fix:** Create and populate the venv:

```bash
python3 -m venv /home/ubuntu/streamlit-venv
/home/ubuntu/streamlit-venv/bin/pip install -r requirements.txt
```

Then re-run `_launch_on_ec2.sh`.

---

### §14 — `_launch_on_ec2.sh` → `Error: Invalid value: File does not exist: app.py`

**Symptom:** Streamlit starts but fails to find `app.py`:

```
Error: Invalid value: File does not exist: app.py
```

**Cause:** The launch script `cd`s to `/home/ubuntu` but `app.py` lives in
`/home/ubuntu/M3_Lab_E_Streamlit_Deployment/`.

**Fix:**

```bash
sed -i 's|cd /home/ubuntu$|cd /home/ubuntu/M3_Lab_E_Streamlit_Deployment|' \
    _launch_on_ec2.sh
```

Then re-run `_launch_on_ec2.sh`.

---

### §15 — `batch_score.py` Runs in DEMO MODE Even with Real AWS Up

**Symptom:** `batch_score.py` logs "Running in DEMO MODE" and writes fake predictions,
even though the real AWS stack is running.

**Cause:** Environment variables (`DB_HOST`, `S3_BUCKET`, `DEMO_MODE`, etc.) set by
`_launch_on_ec2.sh` are shell-session-local. They do not persist to a new SSH session.

**Fix:** Re-export the required variables in the new shell before running `batch_score.py`.
Source them from the config file written by `deploy_m3.sh`:

```bash
# Read values from /opt/m3/config.json (written by deploy_m3.sh on EC2)
export DB_HOST=$(jq -r '.rds_endpoint' /opt/m3/config.json)
export S3_BUCKET=$(jq -r '.s3_bucket' /opt/m3/config.json)
export DEMO_MODE=false
# add other vars as needed by config.py

python3 batch_score.py
```

---

### §16 — `batch_score.py` → "No artifacts loadable" (Wrong S3 Key Paths in `config.py`)

**Symptom:** `batch_score.py` logs that it cannot load model artifacts from S3 and falls
back to heuristics.

**Cause:** `config.py` pointed to `models/xgb-truck-model.pkl`, `models/encoder.pkl`,
`models/scaler.pkl`, but Lab C actually uploaded to
`models/truck-delay/xgboost_model.pkl`, `models/truck-delay/encoder.pkl`,
`models/truck-delay/scaler.pkl`.

**Fix:** Edit `config.py` to correct the S3 key constants:

```python
S3_MODEL_KEY   = 'models/truck-delay/xgboost_model.pkl'
S3_ENCODER_KEY = 'models/truck-delay/encoder.pkl'
S3_SCALER_KEY  = 'models/truck-delay/scaler.pkl'
```

---

### §17 — `apply_prediction_pipeline` → `ValueError: Columns must be same length as key`

**Symptom:**

```
ValueError: Columns must be same length as key
```

raised inside `utils.py::_predict_with_lab_c_xgboost` when assigning the OneHotEncoder
output back to the DataFrame.

**Cause:** The function tried to assign a 98-column OHE output into the original 6
categorical column slots — width mismatch.

**Fix:** Rewrote the prediction function to build the feature matrix correctly:

```python
def _predict_with_lab_c_xgboost(df, model, encoder, scaler):
    # 1. One-hot encode categoricals into a new DataFrame
    cat_encoded = encoder.transform(df[CATEGORICAL_FEATURES])
    cat_df = pd.DataFrame(
        cat_encoded,
        columns=encoder.get_feature_names_out(CATEGORICAL_FEATURES),
        index=df.index
    )

    # 2. Scale continuous features into a new DataFrame
    cont_scaled = scaler.transform(df[CONTINUOUS_FEATURES])
    cont_df = pd.DataFrame(
        cont_scaled,
        columns=CONTINUOUS_FEATURES,
        index=df.index
    )

    # 3. Concat with binary/ordinal columns
    binary_df = df[BINARY_FEATURES].reset_index(drop=True)
    X = pd.concat([cont_df, cat_df, binary_df], axis=1)

    # 4. Align to model's expected columns
    X = X.reindex(columns=model.feature_names_in_, fill_value=0)

    return model.predict_proba(X)[:, 1]
```

---

### §18 — Scaler `ValueError: feature names ... missing: - age`

**Symptom:**

```
ValueError: The feature names should match those that were passed during fit.
Feature names seen at fit time but not present now:
- age
```

**Cause:** `config.py` listed `"driver_age"` in `CONTINUOUS_FEATURES`, but the trained
scaler and feature matrix use the column name `"age"`.

**Fix:**

```bash
sed -i 's/"driver_age"/"age"/' config.py
```

> **Warning:** This change alone broke the Streamlit app's SQL query, which aliased
> `d.age AS driver_age`. See §22 for the companion fix.

---

### §19 — `relation "truck_schedule_with_features" does not exist`

**Symptom:** `batch_score.py` fails with:

```
psycopg2.errors.UndefinedTable: relation "truck_schedule_with_features" does not exist
```

**Cause:** `batch_score.py` queries `truck_schedule_with_features`, but this table is
never created by any M3 notebook — it is a gap in the lab materials.

**Fix:** Run a one-off creation script:

```python
import pandas as pd
import boto3
from sqlalchemy import create_engine
import io

# 1. Load truck_schedule_table from RDS
engine = create_engine(f'postgresql://mlops_admin:<PASSWORD>@localhost:5432/mlops_db')
schedule = pd.read_sql('SELECT * FROM truck_schedule_table', engine)

# 2. Download final_features.csv from S3
s3 = boto3.client('s3')
obj = s3.get_object(Bucket='<S3_BUCKET>', Key='data/processed/final_features.csv')
features = pd.read_csv(io.BytesIO(obj['Body'].read()))

# 3. Verify row-order alignment by comparing the delay column
mismatches = (schedule['delay'].values != features['delay'].values).sum()
print(f'Delay column mismatches: {mismatches}')   # expected: 0 / 12,308

# 4. Concat and write to RDS
combined = pd.concat([schedule, features.drop(columns=['delay'])], axis=1)
combined.to_sql('truck_schedule_with_features', engine, if_exists='replace', index=False)
print(f'Created truck_schedule_with_features: {len(combined)} rows')
```

---

### §20 — `relation "predictions" does not exist`

**Symptom:**

```
psycopg2.errors.UndefinedTable: relation "predictions" does not exist
```

raised by the `LEFT JOIN predictions` in `fetch_unscored_records()` — the table doesn't
exist before the first successful batch score run.

**Cause:** `batch_score.py` tries to join `predictions` before it exists. `pandas.to_sql`
with `if_exists='append'` would create it, but only after this SELECT succeeds.

**Fix:** Pre-create the table manually (once):

```sql
CREATE TABLE IF NOT EXISTS predictions (
    truck_id      BIGINT,
    route_id      VARCHAR(50),
    departure_date TIMESTAMP,
    delay_prob    FLOAT,
    delay_pred    INTEGER,
    scored_at     VARCHAR(50)
);
```

Run via psql or via SQLAlchemy:

```python
engine.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    truck_id BIGINT, route_id VARCHAR(50), departure_date TIMESTAMP,
    delay_prob FLOAT, delay_pred INTEGER, scored_at VARCHAR(50)
)
""")
```

---

### §21 — Streamlit App Shows "Heuristic Predictions" Even After §16 Fix

**Symptom:** The Streamlit dashboard still shows "heuristic predictions — model artifacts
not found on S3" after fixing the S3 key paths in `config.py`.

**Cause:** `_launch_on_ec2.sh` runs Streamlit inside the `/home/ubuntu/streamlit-venv/`
virtual environment. This venv did not have `xgboost`, `scikit-learn`, or other model
dependencies installed — only the base packages.

**Fix:**

```bash
/home/ubuntu/streamlit-venv/bin/pip install -r requirements.txt
```

Then re-run `_launch_on_ec2.sh`. The dashboard should now load the real XGBoost model.

---

### §22 — Streamlit Tabs → Scaler `ValueError: missing: age` (SQL Alias Conflict)

**Symptom:** After fix §18, the batch scorer works but the "By Date / By Truck / By Route"
tabs in the Streamlit dashboard raise the same scaler `missing: age` error.

**Cause:** `utils.py::fetch_predictions_data()`'s SQL query aliased `d.age AS driver_age`.
After §18 set `CONTINUOUS_FEATURES` to use `"age"`, the scaler now expects `age` but the
query returns `driver_age`.

**Fix:** Align the SQL alias with the feature name:

```bash
sed -i 's/d.age          AS driver_age,/d.age          AS age,/' utils.py
```

Restart the Streamlit server after this change.

---

### §23 — Teardown: `delete-stack` → `DELETE_FAILED ... DataBucket ... bucket not empty`

**Symptom:**

```
DELETE_FAILED: Resource handler returned message: "The bucket you tried to delete is not
empty (Service: S3, Status Code: 409)"
```

**Cause:** S3 bucket versioning is enabled. `aws s3 rm --recursive` only removes the
current version of each object; old versions and delete markers remain. CloudFormation
fails to delete the bucket.

**Fix:** Use the Python/boto3 pagination script from `04-Teardown.md` to delete all
object versions and delete markers before retrying `delete-stack`. Do not use the AWS CLI
one-liner:

```bash
# UNRELIABLE on Windows Git Bash — don't use:
# aws s3api delete-objects --bucket <BUCKET> \
#   --delete "$(aws s3api list-object-versions ...)"
```

The quoting and escaping of the embedded JSON sub-command breaks under MINGW64.

---

### §24 — Windows Git Bash: `/tmp/...` Paths Fail

**Symptom:** A heredoc to `/tmp/foo.json` reports success, but `aws ... --policy-document
file:///tmp/foo.json` returns "No such file or directory".

**Cause:** On Windows Git Bash, `/tmp/` maps to a Git-internal temp directory that is not
the same path AWS CLI sees when constructing `file://` URIs.

**Fix:** Always write temporary files to the current directory and use a relative path:

```bash
# Wrong:
cat > /tmp/policy.json << 'EOF' ... EOF
aws iam put-role-policy --policy-document file:///tmp/policy.json

# Right:
cat > ./policy.json << 'EOF' ... EOF
aws iam put-role-policy --policy-document file://policy.json
rm ./policy.json   # clean up after
```

---

### §25 — Windows Git Bash Path-Mangling (`/_stcore/health` → `C:/Program Files/Git/...`)

**Symptom:** Any `aws` CLI argument beginning with `/` (e.g. `/ecs/`, `/_stcore/health`,
`/aws/...`) is silently rewritten to a Windows absolute path like
`C:/Program Files/Git/_stcore/health`, causing unexpected errors.

**Cause:** MINGW64 (Git Bash) applies POSIX-to-Windows path conversion to all arguments
that look like absolute paths.

**Fix:** Prefix the command with `MSYS_NO_PATHCONV=1` to disable conversion:

```bash
MSYS_NO_PATHCONV=1 aws logs get-log-events \
  --log-group-name /ecs/<PROJECT_NAME> \
  --region <AWS_REGION>
```

For an entire session:

```bash
export MSYS_NO_PATHCONV=1
```

Add to `~/.bashrc` if this is a persistent issue.
