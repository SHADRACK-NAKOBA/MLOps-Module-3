# Module 3 — FreshBasket Truck Delay Classification: First Cloud ML Deployment

## Project

**FreshBasket Truck Delay Classification** — a binary classifier that predicts whether a
delivery truck will arrive late, based on route, driver, vehicle, and weather features.
This module is the first cloud deployment in the MLOps curriculum.

## What This Module Deploys

All infrastructure is provisioned via CloudFormation using two files in `AWS_setup/`:

| File | Role |
|------|------|
| `AWS_setup/m3_setup.yaml` | CloudFormation template defining all AWS resources |
| `AWS_setup/deploy_m3.sh` | 7-step automated deployment script |

Resources created in a single stack (`m3-stack`):

- **VPC** — dedicated VPC with public subnets, internet gateway, route tables
- **EC2** — Ubuntu instance running MLflow tracking server (port 5000) and Streamlit
  dashboard (port 8501)
- **RDS PostgreSQL** — private subnet, holds 7 truck-delay source tables plus derived tables
  (`truck_schedule_with_features`, `predictions`)
- **S3** — artifact store for processed data (`final_features.csv`), trained model
  objects, and MLflow artifacts
- **IAM roles** — EC2 instance profile, SageMaker execution role
- **Secrets Manager** — stores the RDS master password under
  `<PROJECT_NAME>/rds-master-password`
- **CloudWatch + SNS** — billing alarm wired to an alert email

## Labs

| Lab | File | What It Does |
|-----|------|--------------|
| A | `labs/M3_Lab_A_AWS_Provisioning_from_Console.md` | Read-only architecture walkthrough — verify resources in AWS Console |
| B | `labs/M3_Lab_B_EDA_Feature_Engineering.ipynb` | EDA, feature engineering, output `final_features.csv` (12,308 × 37) to S3 |
| C | `labs/M3_Lab_C_Model_Training_MLflow.ipynb` | Train LR/RF/XGBoost, register model in MLflow Model Registry |
| D | `labs/M3_Lab_D_MLOps_HP_Tuning.ipynb` | PyCaret + Optuna HP tuning on SageMaker (~70 runs) |
| E | `labs/M3_Lab_E_Streamlit_Deployment/` | Streamlit dashboard + batch scorer on EC2 |

## Final Result

| Outcome | Detail |
|---------|--------|
| Live dashboard | `http://<EC2_PUBLIC_IP>:8501` |
| Model | XGBoost, test F1 ≈ **0.6625** |
| MLflow registry | `truck-delay-classifier` v1, stage: **Staging** |
| Batch scorer | Writes to `predictions` table in RDS; nightly cron at 02:00 UTC |

## Key Experiments in MLflow

| Experiment | Purpose |
|------------|---------|
| `truck-delay-classification` | Lab C — 4 baseline runs (LR, RF, XGBoost, tuned XGB) |
| `truck-delay-hp-tuning` | Lab D — ~70 PyCaret/Optuna HP tuning runs |

## Related Docs in This Folder

| File | Contents |
|------|---------|
| `01-Prerequisites.md` | Software, AWS setup, IAM permissions needed |
| `02-Step-by-Step.md` | Full numbered walkthrough of the session |
| `03-Issues-and-Fixes.md` | Every issue hit and its verified fix |
| `04-Teardown.md` | Full verified teardown checklist and commands |
