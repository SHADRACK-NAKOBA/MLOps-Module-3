# Module 3 — Student Manual

**First Cloud ML Development + Cloud Deployment** | 7 hours total

> This is the **deep-dive manual** for Module 3. It tells you the business problem, the dataset, the lab sequence, the deployment workflow, and exactly how to run each lab end-to-end. Read this before class. Refer back during labs when something feels confusing.

For a one-page repo overview see [README.md](README.md). For deployment-only details see [AWS_setup/AWS_SETUP_README.md](AWS_setup/AWS_SETUP_README.md). For ad-hoc DB / S3 testing snippets see [AWS_setup/MANUAL_TESTING_REFERENCE.md](AWS_setup/MANUAL_TESTING_REFERENCE.md).

---

## Table of contents

1. [What you'll build](#1-what-youll-build)
2. [The business problem (Truck Delay Project)](#2-the-business-problem-truck-delay-project)
3. [Module 3 lab roadmap](#3-module-3-lab-roadmap)
4. [Before you start — prerequisites](#4-before-you-start--prerequisites)
5. [Setup — deploy your AWS environment](#5-setup--deploy-your-aws-environment)
6. [Verify the deployment](#6-verify-the-deployment)
7. [Lab A — Manual AWS Provisioning from Console (Tier-2 demo)](#7-lab-a--manual-aws-provisioning-from-console-tier-2-demo)
8. [Lab B — EDA + Feature Engineering](#8-lab-b--eda--feature-engineering)
9. [Lab C — Model Training + MLflow](#9-lab-c--model-training--mlflow)
10. [Lab D — Streamlit Dashboard + Batch Scoring](#10-lab-d--streamlit-dashboard--batch-scoring)
11. [The dataset — full reference](#11-the-dataset--full-reference)
12. [Learning outcomes](#12-learning-outcomes)
13. [Teardown — destroy everything](#13-teardown--destroy-everything)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What you'll build

By the end of Module 3 you'll have:

- A working AWS environment (VPC, EC2 with MLflow, RDS PostgreSQL, S3, IAM role) deployed in your own AWS account
- A 12,308-row × 37-column feature matrix engineered from 7 raw tables
- Three trained classifiers (Logistic Regression, Random Forest, XGBoost) with all experiments tracked in MLflow
- The best model registered in the MLflow Model Registry
- An interactive Streamlit dashboard (Lab D) that lets ops staff query delay predictions live, plus a batch scoring pipeline that writes predictions back to your database on schedule

This is the start of the **spine project** that continues through M4–M8: in M4 you containerize the dashboard; in M5 you deploy it to ECS behind an ALB with CI/CD; in M6 you add drift detection; in M7 you swap features into Hopsworks; in M8 you orchestrate the whole thing with SageMaker Pipelines.

---

## 2. The business problem (Truck Delay Project)

**FreshBasket** is a Pune-based grocery delivery company. Their fleet of ~1,300 trucks delivers fresh produce, dairy, and packaged goods across 20+ Indian cities every day. **About 40% of those deliveries arrive late**, costing:

- ₹15–20 lakhs/month in spoilage returns (refrigerated trucks running over the timing window)
- A Net Promoter Score dropping ~6 points per quarter (customer churn)
- Driver overtime as drivers wait at warehouses for late trucks

**Priya** is FreshBasket's MLOps lead. She wants a classifier that flags shipments likely to be delayed **before they leave the depot**, so the operations team can pre-warn customers, reroute risky shipments, and schedule replacement trucks.

**The target variable** is `truck_schedule_table.delay` — a binary 0/1 column. Roughly 60% on-time, 40% delayed. Recall (catching real delays) matters more than precision (false alarms): a missed delay costs ~₹25,000 in spoilage; a false alarm costs ~₹8,000 in unnecessary rerouting.

---

## 3. Module 3 lab roadmap

| Lab | Title | Format | Duration | What you do |
|---|---|---|---|---|
| **A** | Manual AWS Provisioning from Console | Reference doc (read this once) | 30 min | Walks you through the AWS Console UI to create the M3 infrastructure manually. You don't have to do it manually — `deploy_m3.sh` does it for you — but reading the doc shows you what your CloudFormation template is *actually* creating, which is essential for understanding (and debugging) the cloud architecture. |
| **B** | EDA + Feature Engineering | Hands-on Jupyter notebook | 90 min | Connect to your RDS, profile the 7 raw tables, merge them into one trip-level dataset (12,308 rows), engineer 36 features (weather, traffic, driver, vehicle), save to `final_features.csv`. |
| **C** | Model Training + MLflow | Hands-on Jupyter notebook | 90 min | Train Logistic Regression, Random Forest, and XGBoost on `final_features.csv`. Log every run to MLflow with metrics, hyperparameters, confusion matrices, and feature-importance plots. Register the best model. |
| **D** | Streamlit Dashboard + Batch Scoring | Hands-on Python project | 60 min | Build an interactive Streamlit app that loads the model and serves live predictions filtered by date / truck / route. Also a `batch_score.py` script that scores all unscored trips and writes predictions to a `predictions` table in RDS. |

The deployment-via-`deploy_m3.sh` step happens **once** before any labs start. Total time including setup: ~5 hours of focused work, or 7 hours including instruction.

---

## 4. Before you start — prerequisites

### On your laptop

| What | Why | Verify with |
|---|---|---|
| AWS account with billing alerts | You need to deploy real cloud resources. Each session costs ~₹30. | Log in at console.aws.amazon.com |
| AWS CLI v2 configured | `deploy_m3.sh` shells out to `aws` for everything | `aws sts get-caller-identity` returns your account |
| Python 3.10+ with `boto3`, `psycopg2-binary`, `sqlalchemy`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `scikit-learn`, `xgboost`, `mlflow`, `streamlit`, `joblib`, `pyyaml` | All the notebooks + scripts depend on these | `pip install boto3 psycopg2-binary sqlalchemy pandas numpy matplotlib seaborn scikit-learn xgboost mlflow streamlit joblib pyyaml` |
| Bash shell | `deploy_m3.sh` is bash. Windows users: install Git for Windows and use **Git Bash** (MINGW64). | `bash --version` |
| Git + a GitHub account | You'll be cloning this repo and committing notebooks | `git --version` |

### Optional but recommended

| What | Why |
|---|---|
| DBeaver Community Edition | A GUI SQL client. Useful for ad-hoc exploration of the 7 RDS tables. |
| VS Code with Python + Jupyter extensions | Notebook editing is much better than browser-Jupyter for serious work |

### Your AWS account permissions

Your IAM user (or role) needs `AdministratorAccess` (or scoped permissions for: EC2, VPC, RDS, S3, IAM, Secrets Manager, SSM, CloudFormation, SageMaker, CloudWatch, SNS). For personal study accounts, `AdministratorAccess` is the simplest. For corporate/managed AWS accounts, work with your account admin to ensure those services are allowed.

---

## 5. Setup — deploy your AWS environment

**One-time setup. ~15 minutes. You only do this once per session.** The script is idempotent — re-running it is safe.

### Step 1 — Edit `AWS_setup/config.yaml`

The whole deployment is driven by a single YAML file. Open [`AWS_setup/config.yaml`](AWS_setup/config.yaml) and change these three keys:

```yaml
project_name: mlops-m3-<your-firstname>-2026    # MUST be unique per learner (S3 bucket names are globally unique)
aws_region: ap-south-1                            # Pick the region closest to you (Mumbai = ap-south-1, US East = us-east-1)
alert_email: you@example.com                      # Your email — gets SNS billing alerts
```

Everything else (EC2 instance type, RDS class, storage sizes, Postgres version, allowed SSH CIDR) has a sensible default. Don't change them unless you have a reason.

### Step 2 — Make sure `AWS_setup/data/` has the 7 Truck Delay CSVs

If you cloned this repo and the CSVs aren't there (some setups strip large files), download them from the course's data bundle. See [`AWS_setup/data/DATA_README.md`](AWS_setup/data/DATA_README.md) for filenames and expected sizes.

### Step 3 — Run the deploy script

```bash
cd "Module 3/AWS_setup/"
chmod +x deploy_m3.sh         # first time only
./deploy_m3.sh
```

The script runs 7 steps, end-to-end, in ~15 minutes:

| Step | What | Time |
|---|---|---|
| 0 | Preflight — verifies AWS creds + `data/` folder + checks for stuck previous stack | 5 sec |
| — | Resolves the latest Ubuntu 24.04 LTS AMI for your region from Canonical's AMI catalog | 5 sec |
| — | Creates the EC2 key pair via `aws ec2 create-key-pair` and saves the `.pem` locally | 5 sec |
| 1 | Deploys CloudFormation stack — VPC, 2 subnets, IGW, Security Groups, EC2 (with bootstrap UserData that installs Python 3.12 + Docker + AWS CLI + MLflow), RDS PostgreSQL 15.10, S3 bucket, IAM roles, Secrets Manager for the RDS password | ~5 min |
| 2 | Reads stack outputs (RDS endpoint, S3 bucket name, MLflow URL, secret ARN, etc.) | 5 sec |
| 3 | Confirms the `.pem` is ready locally | 1 sec |
| 4 | Uploads the 7 Truck Delay CSVs to S3 at `s3://<bucket>/data/raw/` | ~2 min |
| 5 | Polls the MLflow URL until the EC2 bootstrap finishes installing everything (3–8 min) | 3–8 min |
| 6 | SCPs `load_csvs.py` to the EC2, then runs it — bulk-loads the 7 CSVs from S3 into RDS via Postgres COPY | ~3 min |
| 7 | Prints a final summary with all endpoints + the next-step instructions | 1 sec |

### Step 4 — Save the endpoints you'll use throughout the labs

When the script finishes, you'll see something like:

```
══════════════════════════════════════════════
  ✔ Deployment complete
══════════════════════════════════════════════

  Stack name:       m3-stack
  AWS region:       ap-south-1
  Bootstrap time:   642s

  ── Endpoints ──
  MLflow UI:        http://<EC2_IP>:5000
  EC2 SSH:          ssh -i mlops-m3-<your-name>-2026-key.pem ubuntu@ec2-...amazonaws.com
  RDS endpoint:     mlops-m3-<your-name>-2026-rds.<id>.<region>.rds.amazonaws.com  (port 5432)
  RDS database:     truck_delay_db
  RDS user:         mlops_admin
  RDS password:     aws secretsmanager get-secret-value --secret-id <secret-arn> ...
  S3 bucket:        s3://mlops-m3-<your-name>-2026-<account-id>
  SageMaker role:   arn:aws:iam::<account-id>:role/mlops-m3-<your-name>-2026-sagemaker-role
```

**Bookmark these values.** You'll paste them into the notebooks in Labs B / C / D. They're also always retrievable later via `aws cloudformation describe-stacks --stack-name m3-stack --region <region>`.

### What if the deploy fails?

The script is idempotent — fix the root cause and re-run. The most common failure modes:

- **`BucketAlreadyExists`** → your `project_name` is colliding with someone else's S3 bucket. Change it in `config.yaml`.
- **`Cannot find version 15.7 for postgres`** → the Postgres version in `config.yaml` isn't available in your region. Run `aws rds describe-db-engine-versions --engine postgres --region <region> --query "DBEngineVersions[*].EngineVersion"`, pick one, update `config.yaml`.
- **Stack stuck in `ROLLBACK_COMPLETE`** → step 0 of the script detects this and offers to delete + recreate. Answer "y" when prompted.
- **`AWS::EarlyValidation::ResourceExistenceCheck`** → eventual consistency. Wait 10 seconds, re-run. If it persists, your account may have an SCP / CloudFormation hook blocking some resource.

See [`AWS_setup/AWS_SETUP_README.md`](AWS_setup/AWS_SETUP_README.md) for the full troubleshooting table.

---

## 6. Verify the deployment

Four verification scripts in `AWS_setup/`. Run them once after the deploy script completes; they confirm everything is healthy before you start the labs.

```bash
cd "Module 3/AWS_setup/"

python verify_ec2.py        # EC2 running, AWS health checks green, SSH port open, MLflow HTTP 200
python verify_s3.py         # S3 bucket exists with all 7 CSVs
python verify_mlflow.py     # MLflow service + REST API + Python-client end-to-end round-trip

# verify_rds.py runs on EC2 (RDS is in the VPC). The deploy script already runs the loader on EC2,
# so technically this isn't required, but it's a useful sanity check that the tables loaded correctly:
PEM=mlops-m3-<your-name>-2026-key.pem
EC2_DNS=$(aws cloudformation describe-stacks --stack-name m3-stack --region <region> \
    --query "Stacks[0].Outputs[?OutputKey=='Ec2PublicDns'].OutputValue" --output text)
scp -i $PEM verify_rds.py ubuntu@$EC2_DNS:~/
ssh -i $PEM ubuntu@$EC2_DNS "python3 verify_rds.py"
```

All four should print `Summary: N PASS, 0 FAIL`. If anything fails, fix it before proceeding to labs — these failures only get harder to diagnose mid-lab.

---

## 7. Lab A — Manual AWS Provisioning from Console (Tier-2 demo)

**Format:** Reference doc. You read it; you don't execute it. ~30 min.

**File:** [`labs/M3_Lab_A_AWS_Provisioning_from_Console.md`](labs/M3_Lab_A_AWS_Provisioning_from_Console.md)

**Why this exists:** the `deploy_m3.sh` script provisions everything via CloudFormation in 15 minutes. That hides the details. Lab A walks you through the exact same 9 AWS services — VPC, subnets, security groups, IAM, EC2, RDS, S3, Secrets Manager, EC2 key pair — but as Console clicks, with the rationale for every checkbox.

After reading Lab A you'll understand:
- Why the VPC needs 2 subnets in different AZs (RDS requires it)
- Why the RDS security group's inbound rule lists "EC2 SG" instead of `0.0.0.0/0` (private DB access)
- Why the EC2 IAM instance profile is what lets the bootstrap script fetch the RDS password (no credentials on the box)
- Why MLflow's systemd unit needs `--allowed-hosts '*'` (MLflow 3.x DNS-rebinding protection)
- What the CloudFormation YAML actually expands to behind the scenes

You don't need to recreate the resources manually. Just read the doc, look at the AWS Console alongside it while skimming, and confirm your understanding.

---

## 8. Lab B — EDA + Feature Engineering

**Format:** Hands-on Jupyter notebook. ~90 min.

**File:** [`labs/M3_Lab_B_EDA_Feature_Engineering.ipynb`](labs/M3_Lab_B_EDA_Feature_Engineering.ipynb)

### What you'll do

11 sections, ~31 code cells:

1. **Environment setup** — install + import libs
2. **Connect to RDS** — psycopg2 + SQLAlchemy engine pointed at *your* RDS (using `mlops_admin` credentials from your Secrets Manager — see the notebook's Section 2 for how to retrieve)
3. **Load + profile each table** — `SELECT *` from all 7 tables, eyeball schemas, row counts, null distributions
4. **Target variable analysis** — class balance + business cost framing
5. **Merge core tables** — schedule + trucks + drivers + routes (4 many-to-one joins; no row growth)
6. **Aggregate traffic** — pre-aggregate the 2.6M-row traffic table to daily averages, then join (the Cartesian-explosion-guard pattern)
7. **Aggregate weather** — three views (route, origin city, destination city) — produces 21 new weather features
8. **Temporal feature engineering** — `hour_of_day`, `day_of_week`, `is_midnight`
9. **EDA** — correlation heatmap, delay rate by categorical features, distributions by class
10. **Assemble final feature matrix** — 12,308 × 37 (36 features + target)
11. **Save artifacts** — `final_features.csv` + `feature_metadata.json` to local disk AND to S3 at `s3://<your-bucket>/data/processed/` (the S3 upload is wrapped in `try/except` so it never crashes the notebook — if your AWS creds aren't set up, you get the local copy only)

### How to run it

The notebook works on **any Python environment with the requirements installed**. Three common options:

| Run from | Setup notes |
|---|---|
| **Your laptop** (recommended for class) | Open the notebook in VS Code or JupyterLab. Make sure your DB connection details (Section 2) point at your own RDS endpoint and use the `mlops_admin` password from Secrets Manager. |
| **A SageMaker Notebook in your AWS account** | Create a `ml.t3.medium` notebook instance, attach the `<project>-sagemaker-role` IAM role from your stack outputs, place it in your VPC (so it can reach RDS via private SG rules). Upload the .ipynb. |
| **Google Colab** | Works if your RDS is publicly accessible. Colab's runtime has many packages preinstalled; you'll need to `!pip install psycopg2-binary mlflow` first. |

### What you'll produce

- `data/processed/final_features.csv` — 12,308 × 37 feature matrix
- `data/processed/feature_metadata.json` — column lists for the next lab
- The same files uploaded to `s3://<your-bucket>/data/processed/` (so Lab C can fetch them from a different SageMaker notebook / laptop / EC2 without needing the local copy)

Lab C reads these directly. Don't lose them between sessions.

---

## 9. Lab C — Model Training + MLflow

**Format:** Hands-on Jupyter notebook. ~90 min.

**File:** [`labs/M3_Lab_C_Model_Training_MLflow.ipynb`](labs/M3_Lab_C_Model_Training_MLflow.ipynb)

### What you'll do

14 sections, ~31 code cells:

1. **Environment setup** — imports + display config
2. **MLflow connection** — point at your EC2 MLflow server (`http://<EC2_IP>:5000`). The notebook gracefully falls back to local-file tracking if your EC2 MLflow isn't reachable.
3. **Load feature matrix** — pull `final_features.csv` from S3 (with a local fallback)
4. **Train / validation / test split** — 70/15/15 stratified on `delay`
5. **Preprocessing** — `OneHotEncoder` (6 categorical → ~98 columns) + `StandardScaler` (27 continuous columns). Fit on train only; transform all three splits. Final matrix: 128 features.
6. **Helper functions** — `log_classification_metrics()` + `plot_confusion_matrix()` for consistent MLflow tracking across all 3 models
7. **Classification metrics primer** — plain-English table mapping precision/recall to FreshBasket's actual ₹ costs
8. **Logistic Regression baseline** — F1 ≈ 0.59, ROC-AUC ≈ 0.75
9. **Random Forest** — F1 ≈ 0.66, ROC-AUC ≈ 0.78 (+0.07 over LR)
10. **XGBoost** — F1 ≈ 0.68, ROC-AUC ≈ 0.80 (+0.02 over RF)
11. **Model comparison** — side-by-side metrics table + grouped-bar chart + overlaid ROC curves
12. **Final test set evaluation** — best model (XGBoost) on the held-out test set
13. **Register best model** — `mlflow.register_model(...)` then transition to "Staging"
14. **Upload artifacts to S3** — model.pkl, encoder.pkl, scaler.pkl, metadata.json

### Where MLflow runs

Each student's stack deploys its **own MLflow server** on the stack's EC2 instance. The systemd unit is configured with `--allowed-hosts '*'` so it's accessible from your laptop / SageMaker notebook over the public IP. The URL is in your stack outputs as `MlflowUiUrl`.

To open the UI in a browser:
```
http://<your_EC2_PublicIp>:5000
```

You'll see your 3 training runs + 1 final-test run + (if you ran `verify_mlflow.py`) the smoke-test runs. Compare runs by clicking and selecting them, or use `mlflow.search_runs(...)` directly in a notebook cell.

### What you'll produce

- `artifacts/xgboost_model.pkl` — the trained classifier
- `artifacts/encoder.pkl` — fitted OneHotEncoder
- `artifacts/scaler.pkl` — fitted StandardScaler
- `artifacts/model_metadata.json` — feature lists + test metrics + version info
- 4 MLflow runs visible in your tracking server
- A registered model in the MLflow Model Registry under name `truck-delay-classifier`, stage = Staging

---

## 10. Lab D — Streamlit Dashboard + Batch Scoring

**Format:** Hands-on Python project (multiple `.py` files + `requirements.txt`). ~60 min.

**Folder:** [`labs/M3_Lab_D_Streamlit_Batch/`](labs/M3_Lab_D_Streamlit_Batch/) (in this repo)

### What is it?

Lab D is the **end-of-M3 capstone**. It takes the trained model from Lab C and exposes it in two complementary ways:

1. **`app.py`** — an **interactive Streamlit dashboard** for FreshBasket's operations team. Three tabs let them query the model's predictions by:
   - **Date** — "Show me all trips scheduled for Jan 15, 2019, ranked by delay risk"
   - **Truck ID** — "What's the delay history for truck #30312694?"
   - **Route ID** — "Which routes (R-...) have the highest predicted delay rate?"
   Each tab displays a colour-coded results table (🟢 low risk / 🟡 moderate / 🔴 high) and a few summary plots.

2. **`batch_score.py`** — a **scheduled batch scoring** pipeline. Cron-style: it runs unattended (e.g., nightly), pulls all unscored trip records from RDS, scores them with the trained model, writes the predictions back to a new `predictions` table in RDS. This is how ops gets a fresh batch of "high-risk trips for tomorrow" delivered to their dashboard every morning.

The two share the same `utils.py` (DB connection, S3 model loader, prediction pipeline) and `config.py` (env-var-driven settings).

### Why we need this

A trained model that lives in an S3 bucket isn't doing any work for the business. Lab D is **where ML meets operations**:

- **Interactive UI** so non-engineers can query the model without writing code
- **Scheduled batch scoring** so predictions are pre-computed and ready when ops staff log in each morning (faster than predicting on demand)
- **A real production pattern** — Streamlit on EC2 + batch job on cron is a perfectly reasonable v1 architecture for many small ML systems. In M4/M5 you'll replace EC2 with Docker → ECS → ALB, but the *shape* of the application (dashboard + batch job) stays the same.

### What's in the folder

```
M3_Lab_D_Streamlit_Batch/
├── app.py                  # Streamlit dashboard entry point — 3 tabs: by Date, by Truck, by Route
├── batch_score.py          # Scheduled scoring script (cron-friendly; idempotent)
├── utils.py                # Shared helpers: SQLAlchemy engine, S3 model loader, prediction pipeline
├── config.py               # Env-var-driven settings (all the AWS endpoints + DB credentials)
├── requirements.txt        # streamlit, pandas, sqlalchemy, psycopg2-binary, boto3, joblib, scikit-learn, xgboost
├── run_live.sh             # Launcher: laptop + SSH tunnel to RDS (option B below)
└── _launch_on_ec2.sh       # Launcher: run directly on the EC2 (option A below — recommended)
```

Both `app.py` and `batch_score.py` share `utils.py` (DB engine, S3 model loader, prediction pipeline) and `config.py` (env-var-driven settings). One source of truth for connection logic; both surfaces use it.

### Settings required to run

The app reads its connection / model details from environment variables (defined in `config.py`):

| Env var | What it is | Where to get it |
|---|---|---|
| `DB_HOST` | RDS endpoint hostname | `RdsEndpoint` from your stack outputs |
| `DB_PORT` | Always `5432` | — |
| `DB_NAME` | Always `truck_delay_db` | — |
| `DB_USER` | Always `mlops_admin` | — |
| `DB_PASSWORD` | RDS master password | `aws secretsmanager get-secret-value --secret-id <RdsMasterPasswordSecretArn> ...` |
| `S3_BUCKET` | Your S3 bucket | `S3BucketName` from your stack outputs |
| `MLFLOW_TRACKING_URI` | Your MLflow URL | `http://<EC2_PublicIp>:5000` |
| `DEMO_MODE` | `false` for live, `true` for synthetic | Set to `false` once your AWS env is up |

Both `run_live.sh` and `_launch_on_ec2.sh` fetch all of these automatically from your CloudFormation stack outputs. You shouldn't need to set them by hand.

### How to run it — three options

**Option A — on the EC2 itself (recommended for class)**

Why: the EC2 already has network reach to RDS + S3, the security group already exposes port 8501, and the MLflow server is right there at `localhost:5000`. No SSH tunnels, no laptop-side environment setup.

```bash
# From AWS_setup/ on your laptop:
EC2_DNS=$(aws cloudformation describe-stacks --stack-name m3-stack --region <region> \
    --query "Stacks[0].Outputs[?OutputKey=='Ec2PublicDns'].OutputValue" --output text)
PEM=mlops-m3-<your-name>-2026-key.pem

# Copy the Lab D folder + your trained model artifacts up to EC2
scp -i $PEM -r ../labs/M3_Lab_D_Streamlit_Batch ubuntu@$EC2_DNS:~/
scp -i $PEM ../labs/artifacts ubuntu@$EC2_DNS:~/M3_Lab_D_Streamlit_Batch/  # the .pkl files from Lab C

# Run the launcher on EC2
ssh -i $PEM ubuntu@$EC2_DNS "bash ~/M3_Lab_D_Streamlit_Batch/_launch_on_ec2.sh"
```

Open `http://<EC2_PublicIp>:8501` in your browser. The Streamlit dashboard renders, you select a date / truck / route, predictions appear.

**Option B — on your laptop with SSH tunnel to RDS**

Why: faster local development. You edit `app.py`, save, Streamlit auto-reloads. The SSH tunnel lets your local Streamlit reach the private RDS via the EC2 jump host.

```bash
# Terminal 1 — establish the SSH tunnel (keep running)
ssh -i mlops-m3-<your-name>-2026-key.pem \
    -L 5432:<RdsEndpoint>:5432 \
    -N ubuntu@ec2-...amazonaws.com

# Terminal 2 — run Streamlit (set DB_HOST=localhost since the tunnel forwards 5432 locally)
cd labs/M3_Lab_D_Streamlit_Batch
DB_HOST=localhost ./run_live.sh
```

Open `http://localhost:8501` in your browser.

**Option C — on a SageMaker Notebook**

Why: SageMaker notebooks have direct access to RDS via the VPC (same as Lab B/C). You can open a JupyterLab terminal and run Streamlit there, then use SageMaker's port-forward proxy to view the UI:

```bash
# In a JupyterLab terminal inside your SageMaker notebook:
cd /home/ec2-user/M3_Lab_D_Streamlit_Batch
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Then visit:
```
https://<your-notebook-name>.notebook.<region>.sagemaker.aws/proxy/8501/
```

### Running the batch scorer

The Streamlit dashboard is interactive — designed for ops staff. The `batch_score.py` script is the unattended counterpart — designed to run nightly via cron:

```bash
# Test it manually first (on the EC2):
ssh -i $PEM ubuntu@$EC2_DNS
cd ~/M3_Lab_D_Streamlit_Batch
python batch_score.py

# Set up a cron job to run every night at 2 AM:
(crontab -l 2>/dev/null; echo "0 2 * * * cd ~/M3_Lab_D_Streamlit_Batch && python batch_score.py >> ~/batch.log 2>&1") | crontab -
```

It reads unscored rows from `truck_schedule_table`, applies the model, writes the results to a new `predictions` table. Idempotent — if a row was already scored, it skips it.

### How Lab D connects to the rest of the project

```
Lab B  ──► final_features.csv (S3)
Lab C  ──► xgboost_model.pkl + encoder.pkl + scaler.pkl (S3 + MLflow Model Registry)
Lab D  ──► reads model from S3 (or MLflow)
        ──► reads live trip data from RDS
        ──► serves UI on port 8501
        ──► batch scorer writes predictions back to RDS

M4 (next module)   ──► containerize app.py with Docker, push to ECR
M5                 ──► deploy the container to ECS with CI/CD
M6                 ──► add drift detection on the batch scorer
M7                 ──► swap S3 model loading for MLflow Registry "Production" stage
M8                 ──► full SageMaker Pipeline orchestrates Lab C → Lab D end-to-end
```

---

## 11. The dataset — full reference

The 7 raw tables live in your RDS PostgreSQL database `truck_delay_db`. The CSVs in `AWS_setup/data/` are the canonical source; `deploy_m3.sh` Step 6 loads them into RDS.

| Table | Rows | Granularity | Role |
|---|---:|---|---|
| `truck_schedule_table` | 12,308 | one row per scheduled trip | **fact table** — has the target `delay` |
| `trucks_table` | 1,300 | one row per truck | vehicle attributes |
| `drivers_table` | 1,300 | one row per driver-truck pair | driver attributes (1:1 with trucks) |
| `routes_table` | 2,352 | one row per route | route metadata (origin, destination, distance) |
| `traffic_table` | 2,597,913 | one row per route-date-hour | **largest** — must aggregate before joining |
| `city_weather` | 55,176 | one row per city-date-hour | hourly weather per city (joined twice: origin + destination) |
| `routes_weather` | 425,712 | one row per route-date | daily weather summary along each route |

For column-level schemas + the ERD see Lab B's notebook (Section 3 walks through each table in detail). For the row-count + size table see [`AWS_setup/data/DATA_README.md`](AWS_setup/data/DATA_README.md).

---

## 12. Learning outcomes

By the end of Module 3 you will be able to:

### Cloud + infrastructure
1. Deploy a multi-resource AWS environment via a single CloudFormation template
2. Read CloudFormation YAML and trace each resource to its purpose in the application
3. SSH into an EC2 instance, inspect systemd services, tail logs
4. Connect to RDS PostgreSQL from Python using `psycopg2` + `SQLAlchemy`
5. Read/write to S3 from Python using `boto3`
6. Understand the role of IAM instance profiles, security groups, and VPC subnets in service-to-service auth
7. Use Secrets Manager to fetch credentials at runtime instead of hardcoding them

### Data engineering
8. Profile a multi-table relational dataset with SQL queries + pandas
9. Engineer features by joining 7 normalized tables into one wide feature matrix
10. Apply pre-aggregation before joining hourly data to a daily fact table (the Cartesian-explosion guard)
11. Handle missing values: median for continuous, "Unknown" for categorical
12. Recognize and prevent target leakage in time-series joins

### Machine learning
13. Train and evaluate three classifiers (Logistic Regression, Random Forest, XGBoost) on the same dataset
14. Choose appropriate metrics for imbalanced binary classification (F1, ROC-AUC over Accuracy)
15. Translate business cost asymmetry (₹25k missed delay vs ₹8k false alarm) into a model selection rationale
16. Interpret feature importance for tree-based models
17. Reason about the validation-vs-test generalization gap

### MLOps tools
18. Connect a Jupyter notebook to a self-hosted MLflow Tracking Server
19. Log parameters, metrics, artifacts, and trained models for every training run
20. Compare runs side-by-side in the MLflow UI + via `mlflow.search_runs()`
21. Register a model in the MLflow Model Registry and transition stages (None → Staging → Production)

### Serving + inference
22. Build an interactive Streamlit web app that loads model artifacts and serves predictions
23. Implement a batch scoring pipeline (read-from-RDS → predict → write-to-RDS)
24. Articulate when to use real-time inference vs. batch scoring

---

## 13. Teardown — destroy everything

**Forgetting to destroy is the #1 cost mistake.** Destroy the stack the moment class ends.

### Before `delete-stack`, do these two preflight cleanups

1. **Delete any SageMaker Notebook Instance you created manually.** If you launched one for Labs B/C, it attached an ENI to your stack's subnet + security group. CloudFormation can't delete the subnet/SG while that ENI exists.
   ```bash
   aws sagemaker list-notebook-instances --region <region> \
       --query "NotebookInstances[*].[NotebookInstanceName,NotebookInstanceStatus]" --output table

   # For each notebook with this stack's IAM role attached:
   aws sagemaker stop-notebook-instance --notebook-instance-name <name> --region <region>
   aws sagemaker wait notebook-instance-stopped --notebook-instance-name <name> --region <region>
   aws sagemaker delete-notebook-instance --notebook-instance-name <name> --region <region>
   ```

2. **Empty the S3 bucket** if MLflow logged artifacts during Lab C (it likely did). The stack's bucket has versioning ON; CloudFormation won't delete versioned objects.
   ```bash
   BUCKET=$(aws cloudformation describe-stacks --stack-name m3-stack --region <region> \
       --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" --output text)

   aws s3 rm "s3://$BUCKET" --recursive --region <region>
   # Plus the versioned objects + delete markers:
   aws s3api delete-objects --bucket "$BUCKET" --region <region> \
       --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --region <region> \
           --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null || true
   aws s3api delete-objects --bucket "$BUCKET" --region <region> \
       --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --region <region> \
           --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null || true
   ```

### Run the teardown

```bash
aws cloudformation delete-stack --stack-name m3-stack --region <region>
aws cloudformation wait stack-delete-complete --stack-name m3-stack --region <region>

# Clean up local files
rm -f mlops-m3-<your-name>-2026-key.pem
```

Takes 5–10 minutes. After it completes:

```bash
# Verify nothing is left
aws cloudformation describe-stacks --stack-name m3-stack --region <region>  # should error: stack not found
aws sagemaker list-notebook-instances --region <region>                       # should be empty
aws s3api list-buckets --query "Buckets[?starts_with(Name, 'mlops-m3-')].Name"  # should not include yours
```

Check the AWS billing dashboard the next day to confirm no surprise charges.

---

## 14. Troubleshooting

| Symptom | First thing to try |
|---|---|
| Can't SSH to EC2: "Permission denied (publickey)" | `chmod 400 *.pem` (works in Git Bash on Windows too) |
| Can't SSH to EC2: "Connection timed out" | EC2 SG may not allow your IP. Confirm `AllowedSshCidr` in `config.yaml`. |
| `psycopg2.OperationalError: connection timed out` from a laptop notebook | Your RDS may not have `PubliclyAccessible: true`. The default in `m3_setup.yaml` makes it private. To allow laptop access either redeploy with public RDS, OR open an SSH tunnel through EC2. |
| MLflow UI shows `ERR_CONNECTION_REFUSED` | EC2 bootstrap may not be finished. Wait until `verify_mlflow.py` passes. |
| MLflow UI shows HTTP 403 | The `--allowed-hosts '*'` flag is missing from the systemd unit. Re-run the latest `m3_setup.yaml`. |
| Bootstrap stuck after 15 min | Did you set `Ec2InstanceType` to `t3.micro`? It OOMs during MLflow pip install. Change to `t3.medium`, destroy + redeploy. |
| Lab C registry call fails with "No XGBoost runs found" | The MLflow filter syntax issue — should be fixed in the current notebook. If you see it, your notebook is stale; pull the latest from GitHub. |
| Lab C cell 16 fails with `KeyError: 'destination_description'` | Same as above — old version of the notebook. Pull the latest. |
| Cost in AWS billing higher than expected | Run the teardown section ASAP. The most common culprit is a SageMaker Notebook Instance left running (`ml.t3.medium` is ~₹4/hr; ~₹3,000/month). |

For more detail see [`AWS_setup/MANUAL_TESTING_REFERENCE.md`](AWS_setup/MANUAL_TESTING_REFERENCE.md) and [`AWS_setup/AWS_SETUP_README.md`](AWS_setup/AWS_SETUP_README.md).

---

*Next module: **M4 — Containerize the Streamlit app with Docker.** The cloud infrastructure from M3 goes away at teardown; in M4 you'll learn to package your work so it can run anywhere, anytime, on any machine.*
