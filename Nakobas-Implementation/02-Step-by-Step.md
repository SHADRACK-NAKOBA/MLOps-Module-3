# Step-by-Step Walkthrough

> Replace all `<PLACEHOLDERS>` with your actual values before running commands.
> Never commit real values — keep them in your shell environment or retrieve from Secrets Manager.

---

## 1. Edit `AWS_setup/config.yaml`

```yaml
project_name: <PROJECT_NAME>    # e.g. mlops-m3
aws_region:   <AWS_REGION>      # e.g. us-east-1
alert_email:  <EMAIL>
billing_alert_threshold_usd: 10
```

- `project_name` is used as a prefix for every AWS resource name.
- `billing_alert_threshold_usd` **must** be a bare number (see `03-Issues-and-Fixes.md` §1).

---

## 2. Run `deploy_m3.sh`

```bash
cd AWS_setup
chmod +x deploy_m3.sh
./deploy_m3.sh
```

The script runs 7 automated steps (allow ~15 minutes total):

| Step | What Happens |
|------|--------------|
| 1 | Validates config and AWS credentials |
| 2 | Creates EC2 key pair, saves `.pem` locally (immediately git-ignored) |
| 3 | Uploads CloudFormation template to S3 |
| 4 | Deploys `m3-stack` via `aws cloudformation create-stack` |
| 5 | Waits for stack to reach `CREATE_COMPLETE` |
| 6 | Bootstraps EC2: installs MLflow, starts tracking server on port 5000 |
| 7 | Prints all output endpoints |

---

## 3. Save Endpoints from Deploy Output

The script prints:

```
MLflow UI:        http://<EC2_PUBLIC_IP>:5000
EC2 SSH:          ssh -i <PROJECT_NAME>-key.pem ubuntu@<EC2_PUBLIC_IP>
RDS endpoint:     <RDS_ENDPOINT>
S3 bucket:        <S3_BUCKET>
SageMaker role:   arn:aws:iam::<AWS_ACCOUNT_ID>:role/<PROJECT_NAME>-sagemaker-role
```

Save these to a local scratch file (not committed). Retrieve any time via:

```bash
aws cloudformation describe-stacks \
  --stack-name m3-stack \
  --region <AWS_REGION> \
  --query "Stacks[0].Outputs"
```

---

## 4. Retrieve RDS Password

```bash
aws secretsmanager get-secret-value \
  --secret-id <PROJECT_NAME>/rds-master-password \
  --region <AWS_REGION> \
  --query SecretString \
  --output text
```

> The secret ID uses a **slash** (`/`), not a hyphen.
> If you get `ResourceNotFoundException`, run `aws secretsmanager list-secrets` to find
> the exact name (see `03-Issues-and-Fixes.md` §3).

---

## 5. Run All 4 Verification Scripts

Before starting labs, SSH to EC2 and run the verify scripts. All must show `PASS`.

```bash
ssh -i <PROJECT_NAME>-key.pem ubuntu@<EC2_PUBLIC_IP>

# On EC2:
python3 verify_ec2.py
python3 verify_s3.py
python3 verify_mlflow.py
python3 verify_rds.py
```

If any show `FAIL`, check the CloudFormation stack events:

```bash
aws cloudformation describe-stack-events \
  --stack-name m3-stack \
  --region <AWS_REGION>
```

---

## 6. Lab A — Architecture Walkthrough (Read-Only)

Open `labs/M3_Lab_A_AWS_Provisioning_from_Console.md` and follow it to cross-check each
deployed resource in the AWS Console:

- **CloudFormation** → `m3-stack` → Resources tab
- **EC2** → Instances → confirm running, note public IP
- **RDS** → Databases → confirm `Available`
- **S3** → confirm bucket exists with `data/`, `models/` prefixes created
- **VPC** → confirm subnets, IGW, route tables
- **IAM** → Roles → confirm `<PROJECT_NAME>-ec2-role`, `<PROJECT_NAME>-sagemaker-role`
- **Secrets Manager** → confirm `<PROJECT_NAME>/rds-master-password`

No code to run; this lab builds intuition for what `deploy_m3.sh` created.

---

## 7. Lab B — EDA & Feature Engineering

**Where:** `labs/M3_Lab_B_EDA_Feature_Engineering.ipynb` — open in VS Code.

**RDS is private** — connect via SSH tunnel in a separate terminal (leave it running):

```bash
ssh -i <PROJECT_NAME>-key.pem \
    -L 5432:<RDS_ENDPOINT>:5432 \
    -N ubuntu@<EC2_PUBLIC_IP>
```

In the notebook's DB_CONFIG cell, set:

```python
DB_HOST = 'localhost'   # NOT <RDS_ENDPOINT> — tunnelled
DB_PORT = 5432
```

Run all **11 sections** in order. Key outputs:

| Output | Location |
|--------|----------|
| `final_features.csv` (12,308 × 37) | `labs/data/processed/` (local) + `s3://<S3_BUCKET>/data/processed/` |
| `feature_metadata.json` | alongside the CSV |

> **Critical:** run cells top-to-bottom. Running DB_CONFIG cells out of order is the
> cause of §5 in the Issues doc.

---

## 8. Lab C — Model Training + MLflow

**Where:** `labs/M3_Lab_C_Model_Training_MLflow.ipynb` — open in VS Code.

Set the MLflow tracking URI before running:

```python
mlflow.set_tracking_uri("http://<EC2_PUBLIC_IP>:5000")
```

Run all **14 sections** in order. What happens:

- Loads `final_features.csv` from S3
- Trains Logistic Regression, Random Forest, XGBoost
- Logs metrics, params, and artifacts to MLflow experiment `truck-delay-classification`
- Registers best model as `truck-delay-classifier` v1 in MLflow Model Registry (stage: Staging)
- Uploads `models/truck-delay/xgboost_model.pkl`, `encoder.pkl`, `scaler.pkl` to S3

**Actual result:** XGBoost test F1 ≈ **0.6625** — record this as your baseline for Lab D.

---

## 9. Lab D — HP Tuning on SageMaker

### 9a. Create a SageMaker Notebook Instance

In the AWS Console → SageMaker → Notebook instances → Create:

| Setting | Value |
|---------|-------|
| Name | `<PROJECT_NAME>-hp-tuning` (or any name) |
| Instance type | `ml.t3.medium` |
| IAM role | `<PROJECT_NAME>-sagemaker-role` (created by the CloudFormation stack) |
| VPC | Select the stack's VPC |
| Subnet | Any public subnet from the stack |

Wait for `InService` status (~3 min), then **Open JupyterLab**.

### 9b. Clone the Repo

In the JupyterLab terminal:

```bash
git clone <REPO_URL> MLOps-Module-3
cd MLOps-Module-3
```

> Linux is case-sensitive — the folder is `MLOps-Module-3`, not `MLOPS-Module-3`
> (see `03-Issues-and-Fixes.md` §7).

### 9c. Install Dependencies

In a notebook cell before imports:

```python
!pip install -q pycaret==3.3.2 optuna mlflow boto3
!pip install -q seaborn matplotlib pandas numpy joblib scikit-learn xgboost
```

### 9d. Configure Environment Variables

```python
import os
os.environ['MLFLOW_TRACKING_URI'] = 'http://<EC2_PUBLIC_IP>:5000'
os.environ['S3_BUCKET']           = '<S3_BUCKET>'
os.environ['BASELINE_F1']         = '0.6625'
```

### 9e. Open and Run the Notebook

Open `labs/M3_Lab_D_MLOps_HP_Tuning.ipynb` → Run All.

- Runtime: **~15–25 minutes**
- Runs: **~70 trials** logged to experiment `truck-delay-hp-tuning` in MLflow
- If you see `ValueError: _CURRENT_EXPERIMENT global variable is not set`, re-run the
  `setup()` cell (see §9 in Issues doc).
- If you see `Exception: Run with UUID ... is already active`, add
  `mlflow.end_run()` before re-running `setup()` (see §10 in Issues doc).

### 9f. Stop and Delete the Notebook Instance

**Do this immediately after the lab to avoid charges.**

AWS Console → SageMaker → Notebook instances → select → Stop → (wait) → Delete.

Or via CLI:

```bash
aws sagemaker stop-notebook-instance \
  --notebook-instance-name <NOTEBOOK_NAME> --region <AWS_REGION>

# Wait for Stopped status, then:
aws sagemaker delete-notebook-instance \
  --notebook-instance-name <NOTEBOOK_NAME> --region <AWS_REGION>
```

---

## 10. Lab E — Streamlit Dashboard + Batch Scorer

### 10a. Copy Lab Files to EC2

```bash
scp -i <PROJECT_NAME>-key.pem -r \
    labs/M3_Lab_E_Streamlit_Deployment/ \
    ubuntu@<EC2_PUBLIC_IP>:~/

scp -i <PROJECT_NAME>-key.pem -r \
    labs/artifacts/ \
    ubuntu@<EC2_PUBLIC_IP>:~/M3_Lab_E_Streamlit_Deployment/
```

### 10b. SSH to EC2 and Install Requirements

```bash
ssh -i <PROJECT_NAME>-key.pem ubuntu@<EC2_PUBLIC_IP>

cd M3_Lab_E_Streamlit_Deployment

# Ubuntu 24.04 needs --break-system-packages (see §11 in Issues doc)
pip install -r requirements.txt --break-system-packages

# Fix CRLF line endings from Windows (see §12 in Issues doc)
sed -i 's/\r$//' _launch_on_ec2.sh
sed -i 's/\r$//' *.sh
```

### 10c. Create the Streamlit Venv (if required by the launch script)

```bash
python3 -m venv /home/ubuntu/streamlit-venv
/home/ubuntu/streamlit-venv/bin/pip install -r requirements.txt
```

### 10d. Launch the Dashboard

```bash
chmod +x _launch_on_ec2.sh
./_launch_on_ec2.sh
```

Dashboard live at: `http://<EC2_PUBLIC_IP>:8501`

Open in your browser and verify the "By Date / By Truck / By Route" tabs load data.

### 10e. Run the Batch Scorer

In a new SSH session (re-export env vars — they don't persist):

```bash
# Source config from the instance metadata file written by deploy_m3.sh
export DB_HOST=<RDS_ENDPOINT>
export S3_BUCKET=<S3_BUCKET>
export DEMO_MODE=false
# (add any other vars expected by config.py)

python3 batch_score.py
```

Verify rows in RDS:

```bash
psql -h localhost -p 5432 -U mlops_admin -d mlops_db \
  -c "SELECT COUNT(*) FROM predictions;"
```

### 10f. Set Up Nightly Cron

```bash
crontab -e
```

Add:

```cron
0 2 * * * cd /home/ubuntu/M3_Lab_E_Streamlit_Deployment && python3 batch_score.py >> /home/ubuntu/batch.log 2>&1
```

Runs daily at 02:00 UTC. Check `~/batch.log` after the first run.

---

## 11. Teardown

See `04-Teardown.md` for the full verified checklist. Summary order:

1. Stop and delete SageMaker notebook instance (if not done in step 9f)
2. Empty S3 bucket — **including all object versions and delete markers** (use the
   boto3 pagination script in `04-Teardown.md`; the AWS CLI one-liner is unreliable on
   Windows Git Bash — see `03-Issues-and-Fixes.md` §23)
3. Delete CloudFormation stack:
   ```bash
   aws cloudformation delete-stack \
     --stack-name m3-stack --region <AWS_REGION>
   ```
4. Delete local `.pem` file: `rm <PROJECT_NAME>-key.pem`
5. Delete AWS-side key pair:
   ```bash
   aws ec2 delete-key-pair \
     --key-name <PROJECT_NAME>-key --region <AWS_REGION>
   ```
6. Verify all resources gone (see `04-Teardown.md` for the verification bash block).
