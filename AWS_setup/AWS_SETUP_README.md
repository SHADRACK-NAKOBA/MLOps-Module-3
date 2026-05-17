# Module 3 — AWS Environment Setup

> **Who this is for:** Anyone deploying the Module 3 infrastructure into an AWS account — instructor (for the demo) or student (for their own per-batch environment). The course is designed so **each student deploys their own m3-stack** in their own AWS account.

This folder contains:

| File / Folder | What it does |
|---|---|
| **`config.yaml`** | **The single source of truth for ALL configuration** — project name, region, instance types, RDS sizing, alert email, etc. Edit this file ONCE; every other file reads from it. |
| `m3_setup.yaml` | The AWS infrastructure for Module 3 in one CloudFormation template — VPC, EC2, RDS, S3, IAM (~470 lines) |
| `load_csvs.py` | Python loader that reads the 7 Truck Delay CSVs from S3 and bulk-inserts them into RDS PostgreSQL. Kept separate from the YAML so it stays lintable, testable, and easy to edit |
| `deploy_m3.sh` | One-shot bash script that runs deployment Steps 1–7 end-to-end (it SCPs `load_csvs.py` into the EC2 in Step 6) |
| `data/` | **Place the 7 Truck Delay CSVs here before running the deploy script.** Path is hardcoded — `./data` is the only place the script looks. See `data/DATA_README.md` for the exact filenames. |
| `verify_ec2.py` / `verify_s3.py` / `verify_rds.py` | Small standalone scripts to verify each service after deployment. Run these to confirm EC2/MLflow, S3 bucket+CSVs, and RDS tables+rows are all healthy. See `MANUAL_TESTING_REFERENCE.md` for usage. |
| `MANUAL_TESTING_REFERENCE.md` | Documents the verify scripts + manual inline snippets (`psql`, ad-hoc `psycopg2`) + troubleshooting recipes. |
| `AWS_SETUP_README.md` | This file — read it first, then run the script |

**Recommended path:** confirm `data/` is populated → edit `config.yaml` (everything is configured there) → run `./deploy_m3.sh`. ~15 min total.

> 📚 **First time on AWS? Want to see what this script does step-by-step?** See [`../labs/M3_LabB_Manual_AWS_Provisioning_from_Console.md`](../labs/M3_LabB_Manual_AWS_Provisioning_from_Console.md) — a Console-based walkthrough of the same 9 AWS services this script provisions (VPC, Security Groups, IAM, EC2, RDS, Secrets Manager, S3). Takes ~90 min the first time but builds the intuition you'll need to debug things later. Do this lab **once**, then use `deploy_m3.sh` for every subsequent session.

---

## What You'll Have After Deployment

| Resource | What You Get | Default Type |
|----------|--------------|--------------|
| VPC + 2 public subnets + Internet Gateway + route table | Network isolation across 2 AZs | 10.0.0.0/16 |
| EC2 Security Group | SSH (22), FastAPI (8000), Streamlit (8501), MLflow (5000), Flask (5001) | — |
| RDS Security Group | PostgreSQL (5432) **from EC2 only** | — |
| **EC2 instance** (**Ubuntu 24.04 LTS**, auto-resolved from Canonical's latest patched AMI) with Python 3.12 + Docker + AWS CLI + MLflow auto-installed | Compute for MLflow server, Streamlit, batch scoring | **t3.medium** (2 vCPU, 4 GB RAM, ~$0.04/hr) |
| EC2 EBS root volume | Storage | 20 GB gp3 |
| EC2 key pair (private key auto-stored in SSM Parameter Store) | SSH access | RSA 4096 |
| **RDS PostgreSQL** with `truck_delay_db` pre-created | Stores 7 Truck Delay tables | **db.t3.small** (2 vCPU, 2 GB RAM), PostgreSQL **15.10**, 20 GB |
| RDS master password (24-char auto-generated, in Secrets Manager) | Credential storage | — |
| **S3 bucket** with versioning + public-access block | Datasets + model artifacts + MLflow artifact store | Standard |
| SageMaker IAM execution role | Attach when creating SageMaker notebooks for Labs C & D | — |
| (Optional) SNS topic + CloudWatch billing alarm at $10 | Cost guardrail | Only created if region is us-east-1 + email provided |

**MLflow auto-starts** as a systemd service on EC2. Visit `http://<EC2_PUBLIC_IP>:5000` after bootstrap completes (3–8 min on the default t3.medium).

**Cost per M3 session** (deploy + same-day destroy): ~₹50–₹70 (~$0.60–$0.85). **Not Free Tier** — see why below.

> ℹ️ **Why the defaults are not Free Tier (t3.medium + db.t3.small).** The earlier-default `t3.micro` (1 GB RAM) OOMs while installing MLflow + numpy/pandas/scipy — bootstrap took 10–15 min and often failed. The earlier-default `db.t3.micro` (1 GB RAM) was tight for the 2.6M-row `traffic_table` COPY and the analytical queries SageMaker runs in Labs C/D. Bumping each to the next tier (t3.medium, db.t3.small) avoids both problems for ~₹4/hr extra — trivial for a class session. If you really need Free Tier, see the Settings Reference at the bottom of this file.

---

## Prerequisites

| Tool | Min Version | Check |
|------|-------------|-------|
| AWS CLI v2 | 2.x | `aws --version` |
| AWS credentials configured | — | `aws sts get-caller-identity` |
| Bash shell | — | Built-in on Mac/Linux; on Windows use **Git Bash** (MINGW64) |
| Python 3 (only used to parse JSON from Secrets Manager) | 3.8+ | `python --version` |

**No CDK, no Node.js, no Terraform.** Just the AWS CLI.

Your AWS user needs permissions for: EC2, VPC, RDS, S3, IAM, SecretsManager, CloudFormation, SNS, CloudWatch, SSM. `AdministratorAccess` is the easy way for a personal training setup.

---

## Per-Learner Customization (MUST DO BEFORE DEPLOYING)

If you're deploying this in your **own AWS account**, you MUST change these three values:

| Required Change | Why |
|-----------------|-----|
| `PROJECT_NAME` | S3 bucket names are globally unique across all AWS accounts. Different learners can't both use `mlops-m3-batch-2026`. Suggested format: `mlops-m3-<your-firstname>-2026` (lowercase, hyphens only, 3–31 chars) |
| `ALERT_EMAIL` | Your own email for SNS billing alerts |
| `AWS_REGION` | Pick the region closest to you. India learners: `ap-south-1` (Mumbai). US: `us-east-1`. EU: `eu-west-1`. **Use the same region everywhere** — SageMaker notebook, S3, RDS must all match. |

Optional (defaults are fine for most cases):
- `EC2_TYPE` / `RdsInstanceClass` — defaults are `t3.medium` and `db.t3.small`. Drop to `t3.micro` / `db.t3.micro` only if you absolutely need Free Tier (expect OOM during MLflow install on EC2 and slow queries on RDS).
- `AllowedSshCidr` — defaults to `0.0.0.0/0` (open SSH). For tighter security, set to `<your-IP>/32` in the YAML.

---

## Deployment Option A — One Script (Recommended)

### 1. Edit `config.yaml`

Open `config.yaml` in this folder — it's the single place where ALL configurable values live. At a minimum, change these three keys:

```yaml
project_name: mlops-m3-<your-name>-2026    # ← change (S3 bucket names are globally unique)
aws_region: ap-south-1                      # ← change if you prefer another region
alert_email: you@example.com                # ← change to your email
```

Everything else (EC2 instance type, RDS class, storage sizes, allowed SSH CIDR, billing threshold, ...) has a sensible default in `config.yaml` — change only what you need.

### 2. Make sure `data/` is populated

The 7 Truck Delay CSVs must already be in `AWS_setup/data/` before you run the script. The script's path to the data folder is **hardcoded** to `./data` (relative to the script). See `data/DATA_README.md` for the file list.

### 3. Run the script

```bash
cd "Module 3/AWS_setup/"
chmod +x deploy_m3.sh         # first time only
./deploy_m3.sh
```

> **PyYAML required.** The deploy script and verify scripts read `config.yaml`, which needs PyYAML. Install once: `pip install pyyaml`. (It's a transitive dependency of `awscli`, so if you installed AWS CLI via pip you already have it.)

The script does Steps 1–7 below automatically:
1. Deploys CloudFormation stack (~5 min)
2. Reads stack outputs
3. Downloads the EC2 private key (`.pem`)
4. Uploads the 7 Truck Delay CSVs to S3 (~150 MB, 1–3 min)
5. Waits for EC2 bootstrap to complete (polls MLflow UI, 3–8 min)
6. **SCPs `load_csvs.py` from this folder to EC2**, then SSHes in and runs it → RDS (3–5 min)
7. Prints a final summary with all endpoints

Total: ~15 min, hands-off. If anything fails, the script stops with a clear error message — see Troubleshooting.

### What if the script fails partway through?

**The script is idempotent — just fix the root cause and re-run `./deploy_m3.sh`.** Every step checks its own work and skips what's already done:

| If it failed at... | Cause | Fix | Cost of re-run |
|---|---|---|---|
| **Step 0 (preflight)** | Missing or incomplete `data/` folder | Place the 7 CSVs into `data/` (see `data/DATA_README.md`), re-run | **Zero AWS resources created** — instant retry |
| **Step 0 (preflight)** | Old `ROLLBACK_COMPLETE` stack from previous failure | Answer "y" to the prompt to delete it; or run `aws cloudformation delete-stack --stack-name m3-stack --region <region>` manually | Just deletes the stuck stack |
| Step 1 (deploy) | Bucket name collision, IAM quota, etc. | Change `PROJECT_NAME` or fix the underlying limit; re-run | `cloudformation deploy` is a no-op for an already-current stack |
| Step 3 (.pem download) | SSM permission error | Fix the IAM permission; re-run | Skips if .pem exists |
| Step 4 (S3 sync) | Network glitch | Re-run | `aws s3 sync` skips files already uploaded |
| Step 5 (bootstrap timeout) | Only happens if you overrode `EC2_TYPE` to `t3.micro` and pip OOM'd | Destroy stack, redeploy with default `EC2_TYPE=t3.medium` | Has to redeploy the EC2 — old stack is broken |
| Step 6 (SSH/SCP/loader) | Transient SSH failure or CSV format error | Fix and re-run | `load_csvs.py` does `DROP TABLE IF EXISTS` — fully replayable |

With the default `t3.medium` + `db.t3.small`, you should never hit a failure that requires destroying the stack. (The one historical failure mode — `t3.micro` OOM during MLflow install — is no longer the default.) Everything else is just "re-run the script."

> 💡 **Why this matters:** The data-folder check is in **Step 0, before any AWS resources are created**. If a student forgets to unzip the CSV bundle, the script bails in 2 seconds with a clear error — no wasted CloudFormation deploy, no half-deployed environment to clean up.

---

## Deployment Option B — Manual Steps (For Learning / Debugging)

If you want to see what the script does, run these manually. Same end state.

### Step 1: Deploy the stack (~5 min)

```bash
aws cloudformation deploy \
    --template-file m3_setup.yaml \
    --stack-name m3-stack \
    --parameter-overrides \
        ProjectName=mlops-m3-batch-2026 \
        AlertEmail=you@example.com \
        Ec2InstanceType=t3.medium \
    --capabilities CAPABILITY_NAMED_IAM \
    --region ap-south-1
```

> `--capabilities CAPABILITY_NAMED_IAM` is required because the template creates an IAM role with a specified name (`<ProjectName>-sagemaker-role`).

### Step 2: Get the stack outputs

```bash
aws cloudformation describe-stacks \
    --stack-name m3-stack \
    --region ap-south-1 \
    --query "Stacks[0].Outputs" \
    --output table
```

Useful outputs:
- `Ec2PublicIp`, `Ec2PublicDns` — for SSH and MLflow URL
- `Ec2KeyPairSsmPath` — where the .pem is stored in SSM
- `RdsEndpoint` — for psycopg2 / DBeaver connections
- `S3BucketName` — for boto3 / `aws s3 cp`
- `SageMakerRoleArn` — attach this when creating SageMaker notebooks
- `MlflowUiUrl` — paste into browser
- Plus **ready-to-paste commands** in `GetKeyCommand`, `SshCommand`, `CsvUploadCommand`, `LoadCsvsCommand`

### Step 3: Download the EC2 private key

Copy-paste the `GetKeyCommand` output, or:

```bash
KEY_PAIR_ID=$(aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
    --query "Stacks[0].Outputs[?OutputKey=='Ec2KeyPairSsmPath'].OutputValue" --output text | awk -F'/' '{print $NF}')

aws ssm get-parameter \
    --name /ec2/keypair/$KEY_PAIR_ID \
    --with-decryption --region ap-south-1 \
    --query Parameter.Value --output text > mlops-m3-batch-2026-key.pem

chmod 400 mlops-m3-batch-2026-key.pem
```

### Step 4: Upload the 7 Truck Delay CSVs to S3

The 7 CSVs must already be in `AWS_setup/data/` (see `data/DATA_README.md` for the file list). From this folder:

```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
    --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" --output text)

aws s3 sync ./data "s3://$BUCKET/data/raw/" --region ap-south-1 --exclude "*.md"
```

~120 MB total. `traffic_table.csv` (~87 MB) is the largest. Takes 1–3 minutes. The `--exclude "*.md"` flag skips `data/DATA_README.md`.

### Step 5: Wait for EC2 bootstrap to complete

EC2 is installing Python 3.12, Docker, AWS CLI, and MLflow via UserData. The marker file `/var/log/m3-bootstrap-complete` is created when done.

```bash
EC2_IP=$(aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
    --query "Stacks[0].Outputs[?OutputKey=='Ec2PublicIp'].OutputValue" --output text)

# Easiest check: is MLflow up?
curl -sI http://$EC2_IP:5000 | head -1     # expect: HTTP/1.1 200 OK

# Or SSH and check the marker file
ssh -i mlops-m3-batch-2026-key.pem ubuntu@$EC2_IP "ls /var/log/m3-bootstrap-complete && echo READY || echo NOT_READY"
```

If still not ready after 15 min, SSH in and check `/var/log/m3-bootstrap.log` for errors. (On the default `t3.medium` this should never time out; OOM is only seen if you forced `t3.micro`.)

### Step 6: Copy `load_csvs.py` to EC2 and run it

The loader script lives **locally** (next to this README), not on the EC2. Copy it over via SCP, then run it on EC2:

```bash
# Copy the loader into the EC2 instance
scp -i mlops-m3-batch-2026-key.pem load_csvs.py ubuntu@$EC2_IP:/home/ubuntu/load_csvs.py

# Move into /opt/m3 (where config.json was placed by UserData), then run
ssh -i mlops-m3-batch-2026-key.pem ubuntu@$EC2_IP \
    "sudo mv /home/ubuntu/load_csvs.py /opt/m3/load_csvs.py && \
     sudo chown ubuntu:ubuntu /opt/m3/load_csvs.py && \
     python3 /opt/m3/load_csvs.py"
```

Takes 3–5 minutes (`traffic_table.csv` has 2.6M rows). Expected output:

```
Loading truck_schedule_table...   →   12,308 rows
Loading trucks_table...           →    1,301 rows
Loading drivers_table...          →    1,301 rows
Loading routes_table...           →    2,353 rows
Loading traffic_table...          → 2,597,914 rows
Loading city_weather...           →   55,177 rows
Loading routes_weather...         →  425,713 rows

All 7 tables loaded successfully.
```

### Step 7: Verify everything

```bash
# Verify MLflow UI loads
curl -sI http://$EC2_IP:5000 | head -1    # HTTP/1.1 200 OK

# Verify RDS row count via psql on EC2
RDS_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id "mlops-m3-batch-2026/rds-master-password" \
    --region ap-south-1 --query SecretString --output text \
    | python -c "import json,sys; print(json.load(sys.stdin)['password'])")

RDS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
    --query "Stacks[0].Outputs[?OutputKey=='RdsEndpoint'].OutputValue" --output text)

ssh -i mlops-m3-batch-2026-key.pem ubuntu@$EC2_IP \
    "PGPASSWORD='$RDS_PASSWORD' psql -h $RDS_ENDPOINT -U mlops_admin -d truck_delay_db -c 'SELECT count(*) FROM truck_schedule_table;'"
# Expect: 12308
```

You're ready for Module 3 labs.

---

## After Deployment — How To Use The Resources

### Lab A & Lab B — already handled
**Lab A (EC2 FastAPI deployment)** was retired from M3 — the same skill is covered in the earlier Pune Price Prediction project (Module 2).

**Lab B (RDS + S3 setup)** was retired as a hands-on lab — every step it walked through (provision RDS, create S3 bucket, create tables, load CSVs, build IAM role) is now done automatically by `m3_setup.yaml` + `load_csvs.py`. The genuinely useful manual snippets from old Lab B — connection test, row-count verification, troubleshooting — live in `MANUAL_TESTING_REFERENCE.md` in this folder.

In-class, Lab B becomes a **Tier 2 walkthrough demo**: instructor opens the AWS Console, shows the resources CloudFormation created (VPC, RDS, S3, IAM), and explains how each maps to a block in `m3_setup.yaml`. See "Instructor-Only: During-Class Tier 2 Demo SOP" at the bottom of this doc.

### For Labs C & D (EDA / Training on SageMaker)
Create a SageMaker Notebook Instance:
1. AWS Console → SageMaker AI → **Notebook instances** → Create
2. Instance type: `ml.t3.medium`
3. IAM role: **paste the `SageMakerRoleArn` from your stack outputs**
4. Network: VPC = your `<PROJECT_NAME>-vpc`, Subnet = `<PROJECT_NAME>-public-a`, Security group = `<PROJECT_NAME>-ec2-sg`
5. Wait ~5 min → click **Open JupyterLab** → upload Lab C / Lab D `.ipynb` files

In the first cell of each notebook, set:
```python
RDS_HOST   = "<RdsEndpoint from stack output>"
RDS_DB     = "truck_delay_db"
RDS_USER   = "mlops_admin"
RDS_PASS   = "<fetch from Secrets Manager — see Step 7 above>"
S3_BUCKET  = "<S3BucketName from stack output>"
MLFLOW_URI = "http://<Ec2PublicIp from stack output>:5000"
```

### For Lab E (Streamlit Batch Scoring on EC2)
SSH to EC2 → `cd /opt/m3 && pip install streamlit && streamlit run app.py`. Port 8501 is open.

---

## Teardown — Run at End of Every Session

**Forgetting to destroy is the #1 cost mistake.** Destroy the stack the moment class ends.

### ⚠️ Two pre-flight steps you MUST do before `delete-stack`

CloudFormation will refuse to delete resources that have dependencies it doesn't know about. Two things you may have created **outside** the stack will block the teardown if you skip them:

**1. Delete any SageMaker Notebook Instances you created manually.** If you launched a notebook in the AWS Console for Labs C / D, it attached an ENI to the stack's subnet + security group. CloudFormation can't delete the subnet/SG while that ENI exists — and CFN doesn't know about your notebook because you created it manually.

   ```bash
   # List your notebooks; copy the name of any matching this stack
   aws sagemaker list-notebook-instances --region ap-south-1 \
       --query "NotebookInstances[*].[NotebookInstanceName,NotebookInstanceStatus]" --output table

   # Delete each one (the notebook must be Stopped first; AWS auto-stops on delete request after a wait)
   aws sagemaker stop-notebook-instance --notebook-instance-name <name> --region ap-south-1   # if Running
   aws sagemaker wait notebook-instance-stopped --notebook-instance-name <name> --region ap-south-1
   aws sagemaker delete-notebook-instance --notebook-instance-name <name> --region ap-south-1

   # Wait until fully gone (~3 min) before continuing — this releases the ENI
   until ! aws sagemaker describe-notebook-instance --notebook-instance-name <name> --region ap-south-1 >/dev/null 2>&1; do sleep 15; done
   ```

**2. Empty the S3 bucket if you uploaded anything beyond the 7 CSVs.** The stack's bucket has Versioning ON. If MLflow logged any artifacts, or if you saved trained models or feature snapshots, those are versioned objects that CloudFormation will NOT delete on its own — the stack delete will fail with `BucketNotEmpty`.

   ```bash
   # Get the bucket name from stack outputs (do this BEFORE deleting the stack)
   BUCKET=$(aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
       --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" --output text)

   # Delete all current objects
   aws s3 rm "s3://$BUCKET" --recursive --region ap-south-1

   # Also wipe every prior version + delete markers (only needed if you added artifacts after deploy)
   aws s3api delete-objects --bucket "$BUCKET" --region ap-south-1 \
       --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --region ap-south-1 \
           --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null || true
   aws s3api delete-objects --bucket "$BUCKET" --region ap-south-1 \
       --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --region ap-south-1 \
           --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null || true
   ```

> If you only uploaded the original 7 CSVs and never ran MLflow / saved models, you can skip step 2 — `cloudformation delete-stack` will handle the original-CSV cleanup. But it's safer to always run it.

### Now run the actual teardown

```bash
aws cloudformation delete-stack --stack-name m3-stack --region ap-south-1
aws cloudformation wait stack-delete-complete --stack-name m3-stack --region ap-south-1

# Clean up local files
rm -f mlops-m3-batch-2026-key.pem
```

Takes 5–10 min. Verify in AWS Console nothing remains under CloudFormation → Stacks (set "View nested" on, "Filter status" to "Any status").

### If the stack ends up in DELETE_FAILED

Most commonly: you skipped pre-flight step 1 (SageMaker notebook still around) or step 2 (bucket has artifacts). Look at `describe-stack-events` for the specific failure reason:

```bash
aws cloudformation describe-stack-events --stack-name m3-stack --region ap-south-1 \
    --query "StackEvents[?ResourceStatus=='DELETE_FAILED'].[Timestamp,LogicalResourceId,ResourceStatusReason]" --output json
```

Fix the blocker (delete the notebook / empty the bucket), then retry `delete-stack`. CloudFormation is idempotent — it picks up where it left off.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `BucketAlreadyExists` | Change `PROJECT_NAME` — S3 bucket names are globally unique across AWS |
| `Cannot find version X.Y for postgres` | The version isn't available in your region. Run `aws rds describe-db-engine-versions --engine postgres --region <region> --query "DBEngineVersions[*].EngineVersion"` and pick one. Update `RdsEngineVersion` default + AllowedValues in the YAML. |
| `Stack in ROLLBACK_COMPLETE state` | Previous deploy failed. Delete first: `aws cloudformation delete-stack --stack-name m3-stack --region <region>` then redeploy. |
| `VcpuLimitExceeded` | You hit your Free Tier EC2 quota. Delete other instances or request a quota increase. |
| `RDS endpoint pending` for 15+ min | Normal first time. If >25 min, check CloudFormation events for error. |
| SSH "Connection timed out during banner exchange" | EC2 bootstrap is CPU-pinned. Wait 5 min or upgrade to `t3.medium`. |
| `Permission denied (publickey)` on SSH | Run `chmod 400 *.pem` (works in Git Bash on Windows too). |
| MLflow UI not loading after 10 min (only when EC2 was forced to `t3.micro`) | OOM on bootstrap. Destroy stack, redeploy with the default `Ec2InstanceType=t3.medium`. |
| MLflow UI shows error after loading | SSH → `sudo systemctl status mlflow` → `sudo journalctl -u mlflow -n 50` |
| `load_csvs.py` "No such file" on EC2 | The script lives locally — it must be SCPed in before running (see Step 6). If you ran `ssh ... python3 /opt/m3/load_csvs.py` directly without SCPing first, that's the cause. |
| `/opt/m3` "Permission denied" on `scp` | The directory was created root-owned by UserData. SCP to `/home/ubuntu/` first, then `sudo mv` into `/opt/m3/` (the deploy script does this for you). |
| `config.json` "No such file" inside loader | EC2 bootstrap didn't finish writing config.json yet. Re-check `ls /var/log/m3-bootstrap-complete` — if missing, wait or check `/var/log/m3-bootstrap.log` for errors. |
| Stack delete hangs | RDS deletion takes 5 min; S3 versioned objects may need manual cleanup |
| Cost > expected | Run `delete-stack` NOW. Check AWS Billing dashboard. |

---

## Settings Reference — Where Each Default Lives

**All customizable settings are at the top of `m3_setup.yaml` in the `Parameters:` section (lines 12–110).**

| What You Want to Change | Parameter Name | Default | Notes |
|------------------------|----------------|---------|-------|
| Stack name prefix (per-learner unique) | `ProjectName` | `mlops-m3-batch-2026` | **MUST be unique per learner** |
| Who can SSH | `AllowedSshCidr` | `0.0.0.0/0` (open) | Set to `<your-IP>/32` for tighter security |
| EC2 instance type | `Ec2InstanceType` | **`t3.medium`** | 2 vCPU, 4 GB RAM. Avoids OOM during MLflow install. Allowed: t2.micro, t2.small, t2.medium, t3.micro, t3.small, t3.medium. Drop to t3.micro only if you need Free Tier (expect OOM during bootstrap). |
| EC2 storage size (GB) | `Ec2VolumeSize` | `20` | Min 8, max 100 |
| Ubuntu AMI | `LatestUbuntuAmiId` | (auto-resolved by `deploy_m3.sh`) | Always set to the latest Ubuntu 24.04 LTS (Noble Numbat) AMI Canonical has published for your region. The script uses `ec2:DescribeImages` filtered by Canonical's owner ID `099720109477` — not editable via config.yaml. |
| RDS instance class | `RdsInstanceClass` | **`db.t3.small`** | 2 vCPU, 2 GB RAM. Comfortable for the 2.6M-row traffic_table COPY and analytical queries in Labs C/D. Allowed: db.t3.micro, db.t3.small, db.t4g.micro, db.t4g.small. Drop to db.t3.micro only if you need Free Tier (expect slow EDA queries). |
| RDS storage (GB) | `RdsAllocatedStorage` | `20` | Min 20, max 100 |
| PostgreSQL version | `RdsEngineVersion` | `15.10` | Allowed: 16.6, 15.18, 15.17, 15.16, 15.10. Versions vary by region. |
| Database name | `RdsDatabaseName` | `truck_delay_db` | The Truck Delay project's database |
| RDS master username | `RdsMasterUsername` | `mlops_admin` | Password auto-generated, kept in Secrets Manager |
| Email for billing alerts | `AlertEmail` | (empty) | Optional |
| Billing alert threshold | `BillingAlertThresholdUsd` | `10` | Only triggers if region is us-east-1 |

You can change these in **two ways**:
1. **Edit defaults in the YAML** — find the `Parameters:` block, change the `Default:` values.
2. **Override at deploy time (recommended — keeps YAML unchanged)** — pass `--parameter-overrides Key=Value` to the deploy command. Example:

```bash
aws cloudformation deploy \
    --template-file m3_setup.yaml \
    --stack-name m3-priya \
    --parameter-overrides \
        ProjectName=mlops-m3-priya-2026 \
        AllowedSshCidr=49.207.x.x/32 \
        AlertEmail=priya@example.com \
    --capabilities CAPABILITY_NAMED_IAM \
    --region ap-south-1
```

> The defaults are `Ec2InstanceType=t3.medium` and `RdsInstanceClass=db.t3.small`, so you only need to override them if you want a different sizing.

---

## Key Pair Management — Where the .pem Lives

The EC2 private key is created by CloudFormation and **stored as an encrypted parameter in AWS Systems Manager (SSM) Parameter Store**, not delivered as a stack output. This is the AWS-recommended pattern — CloudFormation cannot return private keys as outputs without leaking them in CLI logs.

| Aspect | Detail |
|--------|--------|
| Service | AWS Systems Manager Parameter Store |
| Path | `/ec2/keypair/<key-pair-id>` (e.g. `key-0abcd1234567890ef`) |
| Type | SecureString (encrypted with the AWS-managed KMS key `alias/aws/ssm`) |
| Cost | Free |
| Lifetime | Created on `cloudformation deploy`; deleted on `cloudformation delete-stack` |
| Console | Systems Manager → Parameter Store → `/ec2/keypair/...` |

**To retrieve the .pem** — use Step 3 above, or copy the `GetKeyCommand` from stack outputs.

**On Windows**, `chmod 400` works inside Git Bash. From plain PowerShell:
```powershell
icacls .\mlops-m3-batch-2026-key.pem /inheritance:r
icacls .\mlops-m3-batch-2026-key.pem /grant:r "$($env:USERNAME):R"
```

**IAM permissions needed:** `ssm:GetParameter` + `kms:Decrypt` on `alias/aws/ssm`. `AdministratorAccess` covers both.

**Lifecycle:**
| Event | What Happens to the Key |
|-------|------------------------|
| `cloudformation deploy` | Key pair created; private key written to SSM as SecureString |
| Retrieve the .pem | SSM parameter is read; value unchanged. You can retrieve again any time. |
| EC2 stop/start | Key still valid. Public IP changes; SSH command unchanged otherwise. |
| `cloudformation delete-stack` | Key pair deleted from EC2; SSM parameter deleted. Local `.pem` becomes useless. |
| Lost local `.pem` | Re-run the retrieval command — as long as the stack exists, you can re-download. |

**Common mistakes:**
| Mistake | Symptom | Fix |
|---------|---------|-----|
| Forgot `--with-decryption` | `.pem` contains literal `"<encrypted>"` text | Add the flag |
| Skipped `chmod 400` | SSH: "UNPROTECTED PRIVATE KEY FILE" | `chmod 400 *.pem` |
| Wrong region | "ParameterNotFound" | Match `--region` to where the stack lives |
| Lost `.pem` after destroy | Can't SSH; SSM parameter is gone | Redeploy and download fresh |

---

## Cost Estimate

Default config: EC2 `t3.medium` (~₹3.5/hr) + RDS `db.t3.small` (~₹3/hr) + small S3/EBS/data-transfer overhead. Total running cost ~₹7/hr (~$0.08/hr) in ap-south-1.

| Scenario | Cost |
|----------|------|
| 4-hour class session, destroyed same day | **~₹30** (~$0.35) |
| Full 1-day session (8 hrs), destroyed same day | ~₹60 (~$0.70) |
| Free Tier downgrade (t3.micro + db.t3.micro), 4 hrs, destroyed same day | ~₹10 (~$0.12) — but expect bootstrap pain |
| Forgot to destroy, left running 1 week | ~₹1,200 (~$14) |
| Forgot to destroy, left running 1 month | ~₹5,000 (~$60) |

**The dominant cost risk is forgetting to destroy.** Always run `aws cloudformation delete-stack` at the end of every session — the M3 environment isn't designed to persist between sessions.

The billing alarm (if you set `AlertEmail` AND your region is `us-east-1`) will email you when monthly cost exceeds the threshold.

---

## Instructor-Only: During-Class Tier 2 Demo SOP (10–15 min)

At the start of M3, after pre-deploying the stack:
1. **AWS Console → CloudFormation → Stacks → `m3-stack`**
   - Show all 20+ resources in the **Resources** tab
   - "All of this was created by ONE YAML file"
2. **Open `m3_setup.yaml`** in VS Code
   - Walk through the `Parameters:` section
   - Walk through 2–3 `Resources:` entries (Vpc, RdsInstance, Ec2Instance)
3. **Touch each AWS service in Console:**
   - EC2 → show the running instance
   - RDS → show the database with 7 tables loaded
   - S3 → show the bucket with CSVs
   - SageMaker → mention the IAM role is ready for student notebook instances
4. **Bridge to hands-on:** "Now let's open the EDA notebook — Lab C."

---

## File Reference

```
Module 3/AWS_setup/
├── config.yaml                   (SINGLE SOURCE OF TRUTH — all configurable values live here)
├── m3_setup.yaml                 (CloudFormation template — VPC, EC2, RDS, S3, IAM)
├── load_csvs.py                  (S3 → RDS bulk loader — SCPed onto EC2 by the deploy script)
├── deploy_m3.sh                  (One-shot deployment script — reads config.yaml, runs Steps 1–7)
├── verify_ec2.py                 (Verify EC2 + MLflow are healthy — reads config.yaml, runs from laptop)
├── verify_s3.py                  (Verify S3 bucket has the 7 CSVs — reads config.yaml, runs from laptop)
├── verify_rds.py                 (Verify RDS + 7 tables + sample rows — run ON EC2, since RDS is private)
├── data/                         (Hardcoded location for the 7 Truck Delay CSVs)
│   ├── DATA_README.md
│   ├── truck_schedule_table.csv
│   ├── trucks_table.csv
│   ├── drivers_table.csv
│   ├── routes_table.csv
│   ├── traffic_table.csv         (~87 MB — largest)
│   ├── city_weather.csv
│   └── routes_weather.csv
├── MANUAL_TESTING_REFERENCE.md   (Documents the verify scripts + inline manual snippets + troubleshooting)
└── AWS_SETUP_README.md           (This file)
```

No CDK, no Terraform. The loader is plain Python (uses `boto3` + `psycopg2`, both installed on EC2 by UserData).

**Why `load_csvs.py` is separate** (not baked into the YAML as a heredoc): it stays editable as real Python — IDE syntax highlighting works, linters work, you can run it locally against a test DB, and changes don't require redeploying CloudFormation. The deploy script SCPs it onto the EC2 instance in Step 6, after bootstrap finishes writing `/opt/m3/config.json` (which has the RDS endpoint + password the loader needs).

---

*See `../../DELIVERY_MODEL_PIVOT_April_2026.md` for the 3-tier delivery model rationale.*
