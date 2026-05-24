# MLOps Module 3 — First Cloud ML Deployment

This repo contains everything you need to deploy the AWS environment for Module 3 of the AWS MLOps course and run the 5 labs: **AWS provisioning + EDA + Model Training + MLOps HP Tuning + Streamlit Deployment**, all built around a Truck Delay Classification project for FreshBasket Logistics.

> **New to this module?** Start with **[M3_Student_Manual.md](M3_Student_Manual.md)** — the comprehensive walkthrough. The rest of this README is a quick-reference index.

> **Joining at Module 4 (Docker)?** You don't need to run all of M3. You need three things:
> 1. The four files in [`labs/M3_Lab_E_Streamlit_Deployment/`](labs/M3_Lab_E_Streamlit_Deployment/): `app.py`, `config.py`, `utils.py`, `requirements.txt`. M4 Lab 1 copies these into your Docker build context.
> 2. Docker Desktop installed locally (`docker --version` works).
> 3. AWS CLI configured — only required for M4 Lab 3 (push to ECR).
>
> You can skim **[M3_Student_Manual.md §1 and §3](M3_Student_Manual.md)** for ~5 min of context on what the app does. The dashboard runs in `DEMO_MODE=true` with synthetic data, so M4 Labs 1, 2, and 4 work end-to-end without any AWS deployment. Skip the rest of this README.

---

## Repo map

```
.
├── README.md                                 ← you're here
├── M3_Student_Manual.md                      ← THE manual — read this first
│
├── AWS_setup/                                ← deployment tooling (run this once per session)
│   ├── config.yaml                              single source of truth for all settings
│   ├── m3_setup.yaml                            CloudFormation template (VPC, EC2, RDS, S3, IAM)
│   ├── deploy_m3.sh                             one-shot deploy script
│   ├── load_csvs.py                             S3 → RDS bulk loader (runs on EC2 via the deploy script)
│   ├── verify_ec2.py                            health check: EC2 + MLflow
│   ├── verify_s3.py                             health check: S3 bucket + 7 CSVs present
│   ├── verify_rds.py                            health check: RDS connection + 7 tables + sample rows
│   ├── verify_mlflow.py                         health check: MLflow tracking server end-to-end
│   ├── AWS_SETUP_README.md                      deployment deep-dive
│   ├── MANUAL_TESTING_REFERENCE.md              ad-hoc SQL / Python testing snippets
│   └── data/                                    7 Truck Delay CSVs (uploaded to S3 at deploy time)
│       └── DATA_README.md
│
└── labs/
    ├── M3_Lab_A_AWS_Provisioning_from_Console.md   Tier-2 demo: what deploy_m3.sh creates, via Console clicks
    ├── M3_Lab_B_EDA_Feature_Engineering.ipynb      Hands-on: 7 raw tables → 12,308 × 37 feature matrix
    ├── M3_Lab_C_Model_Training_MLflow.ipynb        Hands-on: LR + RF + XGBoost with full MLflow tracking
    ├── M3_Lab_D_MLOps_HP_Tuning.ipynb              Hands-on: PyCaret AutoML + HP tuning, beats Lab C baseline
    ├── M3_Labs_D_and_E_Guide.md                    Walkthrough for Labs D + E (what, how, where, ops)
    └── M3_Lab_E_Streamlit_Deployment/              Hands-on: dashboard + batch scorer (uses Lab D model if better)
        ├── app.py                                   Streamlit UI (interactive predictions)
        ├── batch_score.py                           Scheduled batch scoring (cron-friendly)
        ├── utils.py                                 DB engine + 3-tier model loader + prediction dispatch
        ├── config.py                                env-var-driven settings
        ├── requirements.txt                         pip dependencies
        ├── run_live.sh                              launcher: laptop + SSH tunnel to RDS
        └── _launch_on_ec2.sh                        launcher: run on the EC2 (port 8501 already open)
```

## Quick start (deployment)

```bash
cd "AWS_setup/"

# 1. Edit config.yaml — change project_name / aws_region / alert_email
nano config.yaml

# 2. Make sure the 7 CSVs are in data/ (they should already be — see data/DATA_README.md)

# 3. Deploy (~15 minutes, end-to-end)
chmod +x deploy_m3.sh
./deploy_m3.sh

# 4. Verify everything is healthy
python verify_ec2.py && python verify_s3.py && python verify_mlflow.py
```

When the script finishes you'll have an EC2 with MLflow, an RDS PostgreSQL with the 7 truck-delay tables loaded, an S3 bucket with the raw CSVs, plus a SageMaker IAM role you can attach to notebook instances for Labs B, C, and D.

## After deployment — run the 5 labs

The order matters. Each lab consumes the artifacts the previous one produced.

| Lab | What | Where to run | Output |
|---|---|---|---|
| **A** | [Manual provisioning walkthrough](labs/M3_Lab_A_AWS_Provisioning_from_Console.md) | Read it; don't execute | Mental model of the cloud architecture |
| **B** | [EDA + Feature Engineering notebook](labs/M3_Lab_B_EDA_Feature_Engineering.ipynb) | Local Jupyter / VS Code / SageMaker / Colab | `final_features.csv` (12,308 × 37) |
| **C** | [Model Training + MLflow notebook](labs/M3_Lab_C_Model_Training_MLflow.ipynb) | Same as Lab B | XGBoost model + encoder + scaler + 4 MLflow runs (F1 ≈ 0.679) |
| **D** | [MLOps — HP Tuning notebook](labs/M3_Lab_D_MLOps_HP_Tuning.ipynb) | SageMaker (PyCaret install is heavy) | ~70 MLflow runs in a new experiment, registers v2 of model if it beats baseline |
| **E** | [Deployment using Streamlit](labs/M3_Lab_E_Streamlit_Deployment/) | Best on the EC2 (port 8501 open) | Live UI at `http://<EC2_IP>:8501` — auto-picks Lab D tuned model if better, else Lab C XGBoost |

Walkthrough for Labs D + E (what they do, how to run, where, operations): **[labs/M3_Labs_D_and_E_Guide.md](labs/M3_Labs_D_and_E_Guide.md)**.
Full per-lab walkthrough is in **[M3_Student_Manual.md](M3_Student_Manual.md)**.

## Teardown

Run at the end of every session to avoid surprise AWS bills.

```bash
# Two preflight cleanups (CloudFormation can't undo these for you):
#   - Delete any SageMaker Notebook Instance you created manually
#   - Empty the S3 bucket (versioned objects need explicit deletion)

# Then:
aws cloudformation delete-stack --stack-name m3-stack --region <your-region>
aws cloudformation wait stack-delete-complete --stack-name m3-stack --region <your-region>
rm -f *.pem
```

Full teardown procedure (with copy-paste-ready commands for the preflight steps) is in **[M3_Student_Manual.md](M3_Student_Manual.md) §13** and **[AWS_setup/AWS_SETUP_README.md](AWS_setup/AWS_SETUP_README.md)**.

## What you'll learn

- Deploy a complete AWS environment from a single CloudFormation template
- Engineer 36 features from 7 normalized tables, avoiding the Cartesian-explosion trap
- Train 3 classifiers and track every experiment with MLflow on a self-hosted EC2 server
- Use AutoML (PyCaret) to sweep ~15 algorithms, tune the winner, and only promote it when it genuinely beats the baseline
- Register a model in the MLflow Model Registry and transition stages
- Build a Streamlit dashboard + batch scoring pipeline that ops staff can actually use, with the deployed model auto-selected from the latest "best on test" artifact
- Tear it all down cleanly so it costs nothing tomorrow

Full learning outcomes (24 items, organized by domain) in **[M3_Student_Manual.md](M3_Student_Manual.md) §12**.

## License + credits

Course content built for the **AWS MLOps Master Course** (48 hours, 8 modules). Module 3 is the entry point into the "spine project" — Truck Delay Classification — that continues through M4 (Docker) → M5 (ECS + CI/CD) → M6 (drift detection) → M7 (Hopsworks feature store) → M8 (SageMaker Pipelines).

Synthetic dataset based on a real-world logistics use case at "FreshBasket Logistics" — a fictional Pune-based grocery delivery company with 1,300 trucks and a 40% delay problem.
