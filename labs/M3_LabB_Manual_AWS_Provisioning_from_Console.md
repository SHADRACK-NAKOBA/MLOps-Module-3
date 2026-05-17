# M3 Lab B — Manual AWS Provisioning from the Console

> **Who this is for:** students who want to **see and click** every AWS service that Module 3 needs, instead of running `deploy_m3.sh`. By the time you finish this lab you'll know exactly what each AWS Console screen looks like, what every field means, and why a particular checkbox matters.
>
> **Time:** ~75-90 minutes the first time you do it.
>
> **Cost:** ~₹30 (~$0.35) if you destroy everything the same day. The biggest cost risk is leaving RDS + EC2 running overnight — set a reminder.
>
> **The alternative:** `AWS_setup/deploy_m3.sh` builds everything in this lab via one command in ~15 min. Use that for actual class delivery; use this Console walkthrough to *understand* what that script is doing.

---

## Table of contents

1. [The 9 AWS services you'll provision (and why)](#1-the-9-aws-services-youll-provision-and-why)
2. [Prerequisites](#2-prerequisites)
3. [Pick your unique project prefix](#3-pick-your-unique-project-prefix)
4. **The 9 provisioning steps**
   1. [Step 1: VPC + Subnets + Internet Gateway + Route Table](#step-1-vpc--subnets--internet-gateway--route-table)
   2. [Step 2: Security Groups (EC2 SG + RDS SG)](#step-2-security-groups-ec2-sg--rds-sg)
   3. [Step 3: IAM Role for SageMaker](#step-3-iam-role-for-sagemaker)
   4. [Step 4: EC2 Key Pair](#step-4-ec2-key-pair)
   5. [Step 5: EC2 Instance (Ubuntu, t3.medium, with bootstrap)](#step-5-ec2-instance-ubuntu-t3medium-with-bootstrap)
   6. [Step 6: Secrets Manager secret for the RDS password](#step-6-secrets-manager-secret-for-the-rds-password)
   7. [Step 7: RDS PostgreSQL Instance](#step-7-rds-postgresql-instance)
   8. [Step 8: S3 Bucket + Upload the 7 CSVs](#step-8-s3-bucket--upload-the-7-csvs)
   9. [Step 9: Load CSVs into RDS (SSH from your laptop)](#step-9-load-csvs-into-rds-ssh-from-your-laptop)
5. [End-to-end verification](#5-end-to-end-verification)
6. [Teardown — destroy everything from the Console](#6-teardown--destroy-everything-from-the-console)
7. [Cost awareness](#7-cost-awareness)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. The 9 AWS services you'll provision (and why)

| # | Service | What it does for M3 |
|---|---------|---------------------|
| 1 | **VPC + 2 Subnets + IGW + Route Table** | Networking boundary. All other resources live inside this VPC. RDS specifically requires subnets in 2 AZs (a "DB Subnet Group"). The Internet Gateway + route table give your EC2 outbound internet access for `apt`/`pip` downloads. |
| 2 | **EC2 Security Group** | Firewall for the EC2 server. Opens SSH (22), MLflow (5000), Flask SBERT (5001), FastAPI (8000), Streamlit (8501). |
| 3 | **RDS Security Group** | Firewall for the database. Opens PostgreSQL (5432) ONLY to traffic from the EC2 Security Group — never to the public internet. |
| 4 | **IAM Role for SageMaker** | Lets your SageMaker Notebook (used in Labs C and D) read your S3 bucket, list VPC resources, and attach a network interface in your VPC. |
| 5 | **EC2 Key Pair** | RSA keypair for SSH access. AWS keeps the public half; you save the private half (`.pem`) on your laptop. |
| 6 | **Secrets Manager secret** | Stores the RDS master password (auto-generated, 24 random chars). Never hardcoded; the EC2 instance reads it on demand. |
| 7 | **EC2 Instance** | Multi-purpose Linux server (Ubuntu 24.04, t3.medium). Runs MLflow tracking server (port 5000), Streamlit (8501), FastAPI (8000), and the CSV loader. A bootstrap script (UserData) installs everything automatically on first boot. |
| 8 | **RDS PostgreSQL Instance** | Holds the 7 Truck Delay tables. PostgreSQL 15.10, `db.t3.small`, private (not reachable from the internet — only from EC2). |
| 9 | **S3 Bucket** | Stores raw CSVs (`data/raw/`), MLflow artifacts, trained models, feature snapshots. Versioning ON, public access BLOCKED. |

---

## 2. Prerequisites

| What | Why | How to verify |
|------|-----|---------------|
| AWS account with `AdministratorAccess` (or equivalent permissions for EC2, VPC, RDS, S3, IAM, Secrets Manager) | You need to create resources across multiple services | AWS Console → IAM → Users → your username → Permissions tab |
| AWS Console open in a browser | This whole lab is Console-based | https://console.aws.amazon.com |
| AWS region picked | All your resources must be in the **same** region — pick the one closest to you | Top-right corner of AWS Console. India: `ap-south-1` (Mumbai). US East: `us-east-1`. |
| The 7 Truck Delay CSVs on your laptop | You'll upload them in Step 8 | Find them under `AWS_setup/data/` in this repo |
| AWS CLI v2 installed (for one verification command + the final SCP/SSH) | Some checks are easier in the CLI than the Console | `aws --version` |
| Python 3 + `psycopg2-binary` + `boto3` (for the verification scripts only) | To run `verify_rds.py` on EC2 in Step 9 | `python --version` |

> **One-time setup:** AWS Console → top-right region selector → pick your region. **Keep this same region selected throughout the lab.** Switching regions mid-way is the #1 cause of "I created the SG but can't find it" confusion.

---

## 3. Pick your unique project prefix

You'll use this prefix as the name of almost every resource (so resources don't clash if classmates share an AWS account, and so your S3 bucket name is globally unique).

**Pick something like:** `mlops-m3-priya-2026` — lowercase, hyphens only, 3-31 chars, must start with a letter.

Write it down — you'll type it a lot. We'll refer to it as `<PROJECT>` from here on.

---

## Step 1: VPC + Subnets + Internet Gateway + Route Table

**Why first:** every other resource (EC2, RDS, Security Groups, SageMaker) needs to specify a VPC and Subnet. We use the "VPC and more" wizard which creates all 5 networking resources in one shot.

### Console clicks

1. AWS Console → top-left search bar → type `VPC` → click the **VPC** service
2. Left sidebar → **Your VPCs** → click **Create VPC** (orange button, top right)
3. At the top, select **VPC and more** (not "VPC only" — that gives you fewer fields)
4. Fill in the fields:

   | Field | Value |
   |---|---|
   | Name tag auto-generation | `<PROJECT>` (e.g. `mlops-m3-priya-2026`) |
   | IPv4 CIDR block | `10.0.0.0/16` |
   | IPv6 CIDR block | (leave default — No IPv6) |
   | Tenancy | Default |
   | **Number of Availability Zones (AZs)** | **2** |
   | **Number of public subnets** | **2** |
   | **Number of private subnets** | **0** (we don't need them in M3) |
   | NAT gateways | **None** (saves cost; we don't need them) |
   | VPC endpoints | None |
   | DNS options | leave both **"Enable DNS hostnames"** and **"Enable DNS resolution"** checked |

5. Click **Create VPC** (orange button, bottom right)
6. Wait ~30 sec while AWS spins up the VPC, 2 subnets, an Internet Gateway, a route table, and the associations
7. When you see "✅ Workflow: Create VPC", click **View VPC**

`[SCREENSHOT: VPC and more wizard with all 6 resource bubbles checkmarked green]`

### Verify in the Console

- Left sidebar → **Your VPCs** → you should see `<PROJECT>-vpc` with state "Available"
- Left sidebar → **Subnets** → you should see `<PROJECT>-subnet-public1-az1` and `<PROJECT>-subnet-public2-az2` in different AZs
- Left sidebar → **Internet gateways** → you should see one attached to your VPC
- Left sidebar → **Route tables** → you should see `<PROJECT>-rtb-public` with a route `0.0.0.0/0 → igw-...`

### Verify from the terminal

```bash
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=<PROJECT>-vpc" \
    --query "Vpcs[0].[VpcId,CidrBlock,State]" --output table
```

Expected: one row, state `available`, CIDR `10.0.0.0/16`.

### Common gotcha

If you accidentally selected 1 AZ instead of 2, RDS creation in Step 7 will fail with `"DB Subnet Group must have at least 2 AZs"`. Delete the VPC and redo this step.

---

## Step 2: Security Groups (EC2 SG + RDS SG)

**Why two SGs:** the EC2 SG defines who can reach the EC2 instance (you, the world). The RDS SG defines who can reach the database (only the EC2 instance). The "RDS allows traffic from EC2 SG" rule is the critical security boundary — it means your database is **never** reachable from the public internet, even though it's in a public subnet.

### Create the EC2 Security Group

1. VPC service → left sidebar → **Security groups** → **Create security group**
2. Fields:

   | Field | Value |
   |---|---|
   | Security group name | `<PROJECT>-ec2-sg` |
   | Description | `SSH, FastAPI, Streamlit, MLflow, Flask` |
   | VPC | select **`<PROJECT>-vpc`** (NOT the default VPC!) |

3. **Inbound rules** — click **Add rule** five times and add:

   | Type | Protocol | Port range | Source | Description |
   |------|----------|------------|--------|-------------|
   | SSH | TCP | 22 | Anywhere-IPv4 (`0.0.0.0/0`) | SSH |
   | Custom TCP | TCP | 5000 | Anywhere-IPv4 | MLflow tracking UI |
   | Custom TCP | TCP | 5001 | Anywhere-IPv4 | Flask SBERT |
   | Custom TCP | TCP | 8000 | Anywhere-IPv4 | FastAPI (Lab A) |
   | Custom TCP | TCP | 8501 | Anywhere-IPv4 | Streamlit (Lab E) |

4. **Outbound rules** — leave default (allow all)
5. Click **Create security group**
6. **Copy the new group's ID** (`sg-...`) — you'll need it for the RDS SG below

`[SCREENSHOT: EC2 SG creation with 5 inbound rules listed]`

### Create the RDS Security Group

1. **Create security group** again
2. Fields:

   | Field | Value |
   |---|---|
   | Security group name | `<PROJECT>-rds-sg` |
   | Description | `PostgreSQL 5432 from EC2 SG only` |
   | VPC | `<PROJECT>-vpc` (same as before) |

3. **Inbound rules** — add ONE rule:

   | Type | Protocol | Port range | Source |
   |------|----------|------------|--------|
   | PostgreSQL | TCP | 5432 | **Custom** → paste the EC2 SG ID from above |

   > Critical: **Source = the EC2 Security Group, NOT 0.0.0.0/0.** This is what makes RDS private.

4. Click **Create security group**

### Verify

- VPC → Security groups → both `<PROJECT>-ec2-sg` and `<PROJECT>-rds-sg` should be visible
- Click `<PROJECT>-rds-sg` → Inbound rules → the source should show "sg-..." (the EC2 SG), NOT "0.0.0.0/0"

### Common gotcha

If the SG drop-down "VPC" defaults to your default VPC, you've created the SG in the wrong VPC and it can't be attached to resources in `<PROJECT>-vpc`. Delete and recreate, paying attention to the VPC field.

---

## Step 3: IAM Role for SageMaker

**Why:** when you create a SageMaker Notebook Instance in Lab C/D, AWS asks "which IAM role should this notebook use?" That role determines what the notebook can do (read S3, list VPC resources, etc.). We create it now so it's ready to paste later.

### Console clicks

1. AWS Console search bar → **IAM** → click the service
2. Left sidebar → **Roles** → **Create role**
3. Trusted entity type: **AWS service**
4. Use case: search for `SageMaker` → select **SageMaker - Execution** → **Next**
5. Permissions: the AWS-managed policy `AmazonSageMakerFullAccess` is already attached. Click **Next**
6. Role details:

   | Field | Value |
   |---|---|
   | Role name | `<PROJECT>-sagemaker-role` |
   | Description | `Execution role for SageMaker Notebooks in M3` |

7. **Create role**

### Attach the S3 policy

1. Open the role you just created (Roles list → click `<PROJECT>-sagemaker-role`)
2. Tab **Permissions** → **Add permissions** → **Attach policies**
3. Search `AmazonS3FullAccess` → tick the checkbox → **Add permissions**

### Add inline VPC-access policy

1. Same role → **Add permissions** → **Create inline policy**
2. Switch from **Visual editor** to **JSON**
3. Paste this:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "ec2:CreateNetworkInterface",
         "ec2:DeleteNetworkInterface",
         "ec2:DescribeNetworkInterfaces",
         "ec2:DescribeVpcs",
         "ec2:DescribeSubnets",
         "ec2:DescribeSecurityGroups"
       ],
       "Resource": "*"
     }]
   }
   ```

4. **Next** → name the policy `VpcAccess` → **Create policy**

### Verify

The role should have these three permissions:
- `AmazonSageMakerFullAccess` (AWS managed)
- `AmazonS3FullAccess` (AWS managed)
- `VpcAccess` (Inline, you just created)

**Copy the role ARN** (top of the role page) — you'll paste it when creating the SageMaker Notebook in Lab C/D.

`[SCREENSHOT: SageMaker role with 2 managed + 1 inline policy in the Permissions table]`

---

## Step 4: EC2 Key Pair

**Why:** the EC2 instance needs an RSA keypair for SSH access. AWS keeps the public half; you download the private half (`.pem`) **once and only once** — there's no way to re-download it.

### Console clicks

1. AWS search → **EC2** → click the service
2. Left sidebar → **Key Pairs** (under "Network & Security")
3. **Create key pair**
4. Fields:

   | Field | Value |
   |---|---|
   | Name | `<PROJECT>-key` |
   | Key pair type | **RSA** |
   | Private key file format | **.pem** (for Linux/Mac/Git-Bash) or **.ppk** (for PuTTY on Windows) |

5. **Create key pair**
6. Your browser will download `<PROJECT>-key.pem`. **Save it somewhere safe** — e.g. next to your `AWS_setup/` folder.

### Lock down the .pem file

On macOS / Linux / Git-Bash on Windows:
```bash
chmod 400 <PROJECT>-key.pem
```

On native Windows (PowerShell):
```powershell
icacls .\<PROJECT>-key.pem /inheritance:r
icacls .\<PROJECT>-key.pem /grant:r "$($env:USERNAME):R"
```

### Verify

- EC2 → Key Pairs → you should see `<PROJECT>-key` with the fingerprint shown
- Your local `.pem` file should be ~3-4 KB

### Common gotcha

If you lost the `.pem`, you cannot SSH into the EC2 instance — there's no way to re-download. Solution: delete the EC2 instance, delete the key pair, create a new one. (Or in real life: use AWS Systems Manager Session Manager to log in without SSH.)

---

## Step 5: EC2 Instance (Ubuntu, t3.medium, with bootstrap)

**Why t3.medium and not t3.micro (Free Tier):** t3.micro has 1 GB RAM. The bootstrap script installs MLflow + numpy + pandas + scipy, which OOMs on 1 GB. t3.medium has 4 GB and finishes the bootstrap in 3-5 min cleanly. Cost is ~₹3.5/hr — negligible for a class session.

### Console clicks

1. EC2 service → left sidebar → **Instances** → **Launch instances**
2. **Name and tags:**
   - Name: `<PROJECT>-server`
3. **Application and OS Images:**
   - Search for `Ubuntu Server 24.04`
   - Pick **Ubuntu Server 24.04 LTS (HVM), SSD Volume Type** — verify the architecture says **64-bit (x86)**
4. **Instance type:**
   - Select **t3.medium**
5. **Key pair (login):**
   - Select `<PROJECT>-key` (created in Step 4)
6. **Network settings** → **Edit:**

   | Field | Value |
   |---|---|
   | VPC | `<PROJECT>-vpc` |
   | Subnet | `<PROJECT>-subnet-public1-az1` |
   | Auto-assign public IP | **Enable** |
   | Firewall (security groups) | **Select existing security group** |
   | Common security groups | tick `<PROJECT>-ec2-sg` |

7. **Configure storage:**
   - Root volume: **20 GiB, gp3**
8. **Advanced details** (expand the section):
   - Scroll to the bottom → **User data** text box → paste the script below:

   ```bash
   #!/bin/bash
   set -e
   exec > /var/log/m3-bootstrap.log 2>&1

   echo "==> Updating apt..."
   export DEBIAN_FRONTEND=noninteractive
   apt-get update -y
   apt-get install -y software-properties-common curl unzip

   echo "==> Installing Python 3.12..."
   add-apt-repository -y ppa:deadsnakes/ppa
   apt-get update -y
   apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip postgresql-client

   echo "==> Installing AWS CLI v2..."
   curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip
   unzip -q /tmp/awscli.zip -d /tmp
   /tmp/aws/install

   echo "==> Installing Docker..."
   apt-get install -y docker.io
   usermod -aG docker ubuntu
   systemctl enable docker
   systemctl start docker

   echo "==> Installing MLflow..."
   python3.12 -m venv /opt/mlflow-venv
   /opt/mlflow-venv/bin/pip install --quiet mlflow boto3 psycopg2-binary

   echo "==> Creating MLflow systemd service..."
   cat > /etc/systemd/system/mlflow.service <<SVC
   [Unit]
   Description=MLflow Tracking Server
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu
   ExecStart=/opt/mlflow-venv/bin/mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///home/ubuntu/mlflow.db
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   SVC
   systemctl daemon-reload
   systemctl enable mlflow
   systemctl start mlflow

   echo "==> Installing Python deps for CSV loader..."
   pip3 install --quiet psycopg2-binary boto3

   mkdir -p /opt/m3
   chown -R ubuntu:ubuntu /opt/m3

   touch /var/log/m3-bootstrap-complete
   echo "==> Bootstrap complete."
   ```

   > This script runs **once**, on first boot. It installs everything the M3 labs need, then writes a marker file `/var/log/m3-bootstrap-complete` so you can tell when it's done.

9. **Summary panel (right side)** → confirm the values → **Launch instance**
10. Wait ~1 min for "Successfully initiated launch of instance"

### Wait for bootstrap to finish (~3-8 min)

The instance state goes to "Running" within ~60 sec, but the **bootstrap script keeps running for several more minutes**. You can tell it's done when:

- **MLflow UI loads** at `http://<PUBLIC_IP>:5000` in your browser
- **OR** SSH in and check: `ls /var/log/m3-bootstrap-complete` (the file exists when done)

### Verify

- EC2 → Instances → `<PROJECT>-server` should be **Running** with `2/2 checks passed`
- Note the **Public IPv4 address** and **Public IPv4 DNS** (you'll use both)
- Try SSH:
  ```bash
  ssh -i <PROJECT>-key.pem ubuntu@<public-dns>
  ```
- Open `http://<public-ip>:5000` in your browser — MLflow UI loads

`[SCREENSHOT: EC2 Instances list showing the server in Running state with green health checks]`
`[SCREENSHOT: MLflow UI at http://<public-ip>:5000]`

### Common gotchas

- **Bootstrap stuck after 15+ min:** you accidentally picked t3.micro. Terminate the instance, relaunch with t3.medium.
- **SSH "Permission denied (publickey)":** you forgot `chmod 400` on the .pem.
- **MLflow URL not loading even after 10 min:** SSH in and check `tail -50 /var/log/m3-bootstrap.log` for errors. Most commonly an `apt` timeout — re-run the relevant step manually.

---

## Step 6: Secrets Manager secret for the RDS password

**Why a secret instead of just typing a password:** putting a password in the RDS creation form means it ends up in your browser's form-autofill cache, in any screen-share recording you make, and in logs if anything fails. Secrets Manager generates a strong random password, encrypts it at rest, and lets you fetch it on demand from EC2.

### Console clicks

1. AWS search → **Secrets Manager** → click the service
2. **Store a new secret** (orange button)
3. **Step 1: Secret type:**
   - Pick **Credentials for Amazon RDS database**
   - Username: `mlops_admin`
   - Password: click **Generate password** → confirm length 24, all character types ON → click **Generate password** again
   - **Copy the generated password somewhere temporary** — you'll paste it in Step 7. We won't be able to read it back from this page after we move on.
   - Encryption key: `aws/secretsmanager` (default)
   - Database: tick **Other database** (the actual RDS won't exist yet — we'll link the secret to it later)
   - Next
4. **Step 2: Configure secret:**
   - Secret name: `<PROJECT>/rds-master-password`
   - Description: `RDS master password for <PROJECT>`
   - Next
5. **Step 3: Configure rotation:**
   - Leave **Automatic rotation OFF** (turn on in production, but not for this class)
   - Next
6. **Step 4: Review** → **Store**

### Verify

- Secrets Manager → Secrets → `<PROJECT>/rds-master-password` should be listed
- Click into it → **Retrieve secret value** → confirm the password is what you copied

`[SCREENSHOT: Secrets Manager page showing the new secret in the list]`

---

## Step 7: RDS PostgreSQL Instance

**Why this is the longest step:** RDS provisioning takes ~6 min once you click "Create database". Go grab coffee.

### First, create the DB Subnet Group

(This is the AWS-mandated container that tells RDS which subnets it's allowed to use.)

1. AWS search → **RDS** → click the service
2. Left sidebar → **Subnet groups** → **Create DB Subnet Group**
3. Fields:

   | Field | Value |
   |---|---|
   | Name | `<PROJECT>-db-subnet-group` |
   | Description | `Subnet group for <PROJECT>` |
   | VPC | `<PROJECT>-vpc` |
   | Availability Zones | **select both** AZs that your subnets are in |
   | Subnets | **select both** `<PROJECT>-subnet-public1-az1` and `<PROJECT>-subnet-public2-az2` |

4. **Create**

### Now create the RDS instance

1. RDS → left sidebar → **Databases** → **Create database**
2. Choose database creation method: **Standard create** (not "Easy create")
3. Engine options:
   - Engine type: **PostgreSQL**
   - Engine version: **PostgreSQL 15.10**
4. Templates: **Free tier** OR **Dev/Test** (either works; we override the instance class below)
5. **Settings:**

   | Field | Value |
   |---|---|
   | DB instance identifier | `<PROJECT>-rds` |
   | Master username | `mlops_admin` (must match Secrets Manager) |
   | Credentials management | **Self managed** (we'll paste the password) |
   | Master password | paste the password you generated in Step 6 |
   | Confirm master password | paste again |

6. **DB instance class:**
   - Select **Burstable classes (includes t classes)**
   - Pick `db.t3.small`
7. **Storage:**
   - Storage type: `gp3`
   - Allocated storage: `20` GiB
   - Storage autoscaling: **disabled** (training only)
8. **Availability & durability:**
   - Multi-AZ deployment: **Do not create a standby instance**
9. **Connectivity:**

   | Field | Value |
   |---|---|
   | Compute resource | **Don't connect to an EC2 compute resource** |
   | Network type | IPv4 |
   | Virtual private cloud (VPC) | `<PROJECT>-vpc` |
   | DB subnet group | `<PROJECT>-db-subnet-group` |
   | Public access | **No** ← critical! Don't make RDS public. |
   | VPC security group | **Choose existing** → select `<PROJECT>-rds-sg` (NOT the default!) |
   | Availability Zone | No preference |
   | Database authentication | Password authentication |

10. **Database authentication:** Password authentication
11. **Monitoring:** uncheck "Enable Enhanced monitoring" (saves cost)
12. **Additional configuration** (expand):
    - Initial database name: **`truck_delay_db`** ← this auto-creates the database; without this you'd have to connect and `CREATE DATABASE` manually
    - Backup retention: **0 days** (training only — in prod, set 7+)
    - Encryption: **Enable encryption** (default)
    - Deletion protection: **leave OFF** (so we can clean up easily)
13. **Estimated monthly costs** — should show ~$30/month (you'll pay ~₹0.50/hour while it's running)
14. **Create database**

### Wait for it

Wait ~6 min while AWS provisions the instance. The RDS dashboard will show:
- "Creating" → "Backing-up" → "Available"

When status is **Available**, copy the **Endpoint** (DNS name like `<PROJECT>-rds.xxxxxxxxxxxx.<region>.rds.amazonaws.com` — the 12-char middle portion is unique to your stack). You'll need it for the loader in Step 9.

### Verify

- RDS → Databases → `<PROJECT>-rds` should show status **Available**
- Click into it → Connectivity & security → **Publicly accessible: No**
- VPC security groups: `<PROJECT>-rds-sg`

`[SCREENSHOT: RDS database details page showing Available status, Publicly accessible: No, RDS SG attached]`

### Common gotchas

- **`Cannot find version 15.7 for postgres`:** the version isn't available in your region. Pick `15.10` (which we use here) or another currently-supported version.
- **Selected the default VPC by mistake:** you'll need to delete and recreate. RDS can't be moved between VPCs.
- **Forgot to type `truck_delay_db` in "Initial database name":** RDS creates without a database. Fix: SSH to EC2, run `psql -h <endpoint> -U mlops_admin` and `CREATE DATABASE truck_delay_db;`.

---

## Step 8: S3 Bucket + Upload the 7 CSVs

**Why S3 versioning + Block Public Access ON:**
- Versioning lets you recover from accidental overwrites.
- Block Public Access is the default-secure setting AWS recommends for any bucket holding training data.

### Create the bucket

1. AWS search → **S3** → click the service
2. **Create bucket** (orange button)
3. **General configuration:**

   | Field | Value |
   |---|---|
   | AWS Region | match your other resources |
   | Bucket name | `<PROJECT>-<your-account-id>` (e.g. `mlops-m3-priya-2026-123456789012`). S3 names are globally unique — using your account ID guarantees uniqueness. |
   | Object Ownership | **ACLs disabled (recommended)** |

4. **Block Public Access settings for this bucket:**
   - Leave **all four sub-options ticked** (block public access in every form)
5. **Bucket Versioning:**
   - **Enable**
6. **Default encryption:**
   - Encryption type: **Server-side encryption with Amazon S3 managed keys (SSE-S3)** (default)
7. **Create bucket**

### Upload the 7 CSVs

The 7 CSVs are in `AWS_setup/data/` on your laptop. Two ways to upload:

**Option 1 — via the Console (easy, but slow for 87 MB file):**
1. Click into the new bucket → **Upload** → **Add folder** → select `AWS_setup/data/`
2. Note: by default the folder name gets prepended to S3 keys. We want keys like `data/raw/<file>.csv`. After upload, you may need to move/rename — easier to use the CLI for this step.

**Option 2 — via AWS CLI (much faster, recommended):**

```bash
cd Module\ 3/AWS_setup/

BUCKET=<PROJECT>-<account-id>      # the bucket name you just created
REGION=ap-south-1                    # your region

aws s3 sync ./data s3://$BUCKET/data/raw/ --region $REGION --exclude "*.md"
```

This uploads all 7 CSVs to `s3://$BUCKET/data/raw/` in parallel — ~1-3 min for ~120 MB.

### Verify

- S3 → click into your bucket → navigate to `data/raw/` → you should see all 7 CSVs
- Or from terminal:
  ```bash
  aws s3 ls s3://$BUCKET/data/raw/ --region $REGION --human-readable
  ```
- **Or** run the verify script: `python verify_s3.py`

`[SCREENSHOT: S3 bucket contents page showing 7 CSV files under data/raw/]`

---

## Step 9: Load CSVs into RDS (SSH from your laptop)

**Why this step can't be done in the Console:** the RDS database is private (no public IP). The Console can't reach into a private VPC to run SQL. The CSV loader has to run from the **EC2 instance** (which can reach RDS via the SG rule we set up).

### Quick way (verifies AND loads at the same time)

The CloudFormation/automation flow uses `AWS_setup/load_csvs.py` which reads `/opt/m3/config.json`. For the manual flow, you have to give the loader the connection details yourself.

1. On your laptop, in the `AWS_setup/` folder, edit `load_csvs.py`'s usage — or, simpler, write a small wrapper that uses the RDS endpoint + Secrets Manager password directly:

   ```bash
   # First, set the RDS endpoint and bucket as env vars (use your values)
   export RDS_HOST=<PROJECT>-rds.xxxxxxxxxxxx.ap-south-1.rds.amazonaws.com   # paste YOUR endpoint here
   export S3_BUCKET=<PROJECT>-<account-id>
   export SECRET_NAME=<PROJECT>/rds-master-password
   ```

2. On the EC2 instance, install the loader dependencies and write a minimal `config.json`:

   ```bash
   PEM=<PROJECT>-key.pem
   EC2_DNS=<paste from EC2 → Instances → Public IPv4 DNS>

   # SCP the loader from AWS_setup/ on your laptop to EC2
   scp -i $PEM ../AWS_setup/load_csvs.py ubuntu@$EC2_DNS:~/

   # SSH in and create /opt/m3/config.json (the file load_csvs.py reads)
   ssh -i $PEM ubuntu@$EC2_DNS
   ```

3. **On EC2** (you're now SSH'd in):

   ```bash
   # Fetch the RDS password from Secrets Manager
   RDS_PASSWORD=$(aws secretsmanager get-secret-value \
       --secret-id <PROJECT>/rds-master-password --region ap-south-1 \
       --query SecretString --output text \
       | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')

   # Write the config file the loader expects
   sudo mkdir -p /opt/m3
   sudo tee /opt/m3/config.json > /dev/null <<EOF
   {
     "region": "ap-south-1",
     "s3_bucket": "<PASTE BUCKET NAME>",
     "rds_host": "<PASTE RDS ENDPOINT>",
     "rds_port": "5432",
     "rds_db": "truck_delay_db",
     "rds_user": "mlops_admin",
     "rds_password": "$RDS_PASSWORD"
   }
   EOF
   sudo chown ubuntu:ubuntu /opt/m3/config.json

   # Move the loader into place and run it
   sudo mv ~/load_csvs.py /opt/m3/load_csvs.py
   sudo chown ubuntu:ubuntu /opt/m3/load_csvs.py
   python3 /opt/m3/load_csvs.py
   ```

   > For EC2 to fetch the secret, your EC2 instance needs IAM permissions to call Secrets Manager. In this manual lab, the EC2 has no instance profile — easiest fix: run `aws configure` on EC2 once and paste your IAM user's access key + secret. (In production, attach an instance profile; we skip that here for simplicity.)

4. Expected output (~3-5 min):
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

### Verify

Easiest: run [`verify_rds.py`](../AWS_setup/verify_rds.py) on EC2:

```bash
scp -i $PEM ../AWS_setup/verify_rds.py ubuntu@$EC2_DNS:~/
ssh -i $PEM ubuntu@$EC2_DNS "python3 verify_rds.py"
```

It prints PASS/FAIL on the 7 tables + a sample SELECT + a sample JOIN.

---

## 5. End-to-end verification

After all 9 steps, run the three verification scripts from [`../AWS_setup/`](../AWS_setup/):

```bash
cd Module\ 3/AWS_setup/

python verify_ec2.py       # EC2 + MLflow healthy (run from laptop)
python verify_s3.py        # S3 bucket has 7 CSVs (run from laptop)
# Then SCP + SSH for verify_rds.py:
PEM=<PROJECT>-key.pem
EC2_DNS=<your EC2 public DNS>
scp -i $PEM verify_rds.py ubuntu@$EC2_DNS:~/
ssh -i $PEM ubuntu@$EC2_DNS "python3 verify_rds.py"
```

All three should exit with `OK`. If any fail, jump to the Troubleshooting section.

---

## 6. Teardown — destroy everything from the Console

**Order matters.** Delete in roughly reverse-dependency order so AWS doesn't refuse with `DependencyViolation`.

### Approximate order

1. **RDS** (longest to delete — start it first)
   - RDS → Databases → `<PROJECT>-rds` → Actions → **Delete**
   - Uncheck "Create final snapshot"; tick "I acknowledge..."; type `delete me`
   - Wait ~5 min for it to fully delete
2. **EC2 instance**
   - EC2 → Instances → select `<PROJECT>-server` → Instance state → **Terminate instance**
3. **S3 bucket**
   - S3 → click your bucket → **Empty** (deletes all objects + versions) → **Delete**
4. **Secrets Manager**
   - Secrets Manager → `<PROJECT>/rds-master-password` → Actions → **Delete secret**
   - In production use 7-day recovery; for this lab pick **No recovery**
5. **IAM Role**
   - IAM → Roles → `<PROJECT>-sagemaker-role` → **Delete**
6. **DB Subnet Group**
   - RDS → Subnet groups → `<PROJECT>-db-subnet-group` → Delete
7. **Security Groups**
   - VPC → Security groups → delete RDS SG first, then EC2 SG
8. **VPC + everything inside it**
   - VPC → Your VPCs → `<PROJECT>-vpc` → Actions → **Delete VPC**
   - In the confirmation, AWS lists everything that will be deleted (subnets, IGW, route table, NACLs, DHCP options) — type `delete` and confirm
9. **EC2 Key Pair**
   - EC2 → Key Pairs → `<PROJECT>-key` → Actions → **Delete**
   - (Your local `.pem` file is now useless — delete it from your laptop too)

### Sanity check

After all 9 are deleted, do a final pass:
- Billing dashboard (top-right account menu → Billing) — confirm nothing under "Recent activity" for RDS or EC2

> **Forgetting to destroy is the #1 cost mistake.** A `db.t3.small` + `t3.medium` left running for a month = ~₹5,000 (~$60).

---

## 7. Cost awareness

| Scenario | Approximate cost |
|---|---|
| Complete this lab + destroy same day (4 hours of resources) | **~₹30** (~$0.35) |
| Run RDS + EC2 for 1 day, forget overnight | ~₹200 (~$2.50) |
| Run for a full week without destroying | ~₹1,400 (~$16) |
| Run for a full month without destroying | ~₹5,000 (~$60) |

The dominant cost is EC2 t3.medium (~₹3.5/hr) + RDS db.t3.small (~₹3/hr). Other services (VPC, IGW, Security Groups, IAM, Secrets Manager) are free or essentially-free.

**Set a calendar reminder for teardown** the moment you create the EC2 and RDS instances. Don't rely on memory.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Can't SSH: `Permission denied (publickey)` | Forgot `chmod 400` on the .pem | `chmod 400 <PROJECT>-key.pem` (or `icacls` on native Windows) |
| Can't SSH: `Connection timed out` | EC2 SG doesn't allow port 22 from your IP, OR EC2 has no public IP | Check the SG inbound rules + EC2 has a public IPv4 address |
| MLflow UI shows `ERR_CONNECTION_REFUSED` even after 15 min | Bootstrap script failed or OOM'd | SSH in, run `tail -50 /var/log/m3-bootstrap.log` to see what failed |
| RDS creation: `Cannot find version 15.7 for postgres` | That version is no longer available in your region | Pick `15.10` (or a current 15.x / 16.x from the drop-down) |
| RDS creation: `DB Subnet Group must span 2 AZs` | Your VPC has only 1 subnet, or both subnets are in the same AZ | Recreate the VPC using "VPC and more" with `Number of Availability Zones = 2` |
| RDS shows Available but `psycopg2` from EC2 hangs | RDS SG isn't allowing traffic from EC2 SG | RDS SG inbound rule: source must be the EC2 Security Group, not your IP |
| `truck_delay_db does not exist` when running the loader | You forgot the "Initial database name" field on RDS creation | SSH to EC2, then `psql -h <RDS endpoint> -U mlops_admin -d postgres -c 'CREATE DATABASE truck_delay_db;'` |
| S3 upload fails with `AccessDenied` | Your IAM user doesn't have `s3:PutObject` on the bucket | Attach `AmazonS3FullAccess` to your IAM user (or use AdministratorAccess for class) |
| `BucketAlreadyExists` | Bucket name already taken globally | Include your AWS account ID in the bucket name |
| SageMaker Notebook creation fails: "role doesn't trust SageMaker" | You created an IAM role but didn't choose "SageMaker" as the trusted entity | Recreate the role with use case = SageMaker |
| Teardown: `DependencyViolation` on subnet/VPC delete | RDS is still attached to the subnet (delete hasn't finished) | Wait until RDS shows "Deleting" → eventually disappears, then retry subnet delete |
| Costs spiking | RDS or EC2 left running past the session | Run the Teardown section ASAP; check Billing dashboard daily |

---

## Where to go from here

You just provisioned the entire M3 infrastructure by hand, through the Console. Now compare it to the automated way:

- Read [`../AWS_setup/AWS_SETUP_README.md`](../AWS_setup/AWS_SETUP_README.md) end-to-end
- Run `./deploy_m3.sh` in a fresh AWS account (or after tearing down) — it builds everything you just clicked through in ~15 min

The point of this lab is **not** that you'll use the Console for production work — it's that when you read `m3_setup.yaml`, every `Resources:` block now maps to a screen you've seen before. CloudFormation isn't magic; it's just clicking these same buttons via an API, in the right order.

Next: open **Lab C** in [`./M3_LabC_EDA_Feature_Engineering.ipynb`](./M3_LabC_EDA_Feature_Engineering.ipynb) to start the actual ML work using the database you just built.
