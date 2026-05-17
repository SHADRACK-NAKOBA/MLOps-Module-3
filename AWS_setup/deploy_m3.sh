#!/usr/bin/env bash
# =============================================================================
#  Module 3 — One-Shot Deployment Script (Steps 1-7 from AWS_SETUP_README.md)
# =============================================================================
#
#  USAGE
#    1. Edit `config.yaml` in this folder. All settings live there —
#       project name, region, instance types, RDS sizing, alert email, etc.
#    2. From this folder:   chmod +x deploy_m3.sh && ./deploy_m3.sh
#
#  WHAT IT DOES
#    Step 1  Deploy CloudFormation stack       (~5 min)
#    Step 2  Read stack outputs
#    Step 3  Download EC2 private key (.pem)
#    Step 4  Upload 7 Truck Delay CSVs to S3   (~1-3 min)
#    Step 5  Wait for EC2 bootstrap            (~3-8 min on t3.medium)
#    Step 6  SCP load_csvs.py to EC2, then SSH and run it  (~3-5 min)
#    Step 7  Print final summary + next steps
#
#  REQUIREMENTS
#    - AWS CLI v2 (`aws --version`)
#    - AWS credentials configured (`aws sts get-caller-identity`)
#    - Bash 4+ (Mac/Linux native; on Windows use Git Bash MINGW64)
#    - Python 3 + PyYAML (`pip install pyyaml`) — for reading config.yaml
#
#  RUN-AGAIN / RESUME-AFTER-FAILURE
#    Every step is idempotent. If the script fails partway through (most common
#    cause: missing CSVs in ./data/), just FIX THE ROOT CAUSE and re-run:
#
#        ./deploy_m3.sh
#
#    Behavior of each step on re-run:
#      Step 0  Validates data folder + AWS creds. FAILS FAST before any AWS calls.
#      Step 1  `cloudformation deploy` is a no-op if the stack is already current.
#              If a previous run left a ROLLBACK_COMPLETE stack, Step 0 offers to
#              delete it first.
#      Step 2  Always re-reads outputs (cheap).
#      Step 3  Skips download if the .pem already exists locally.
#      Step 4  `aws s3 sync` skips files already in S3 with matching size+mtime.
#      Step 5  MLflow poll returns immediately if the UI is already up.
#      Step 6  SCP overwrites; `load_csvs.py` does DROP TABLE IF EXISTS so the
#              load is replayable end-to-end.
#      Step 7  Just prints the summary.
#
#    If the failure is OOM on EC2 bootstrap (t3.micro), see Troubleshooting in
#    AWS_SETUP_README.md — the fix is delete-and-redeploy with t3.medium.
# =============================================================================

set -euo pipefail

# =====================================================================
#  CONFIG — single source of truth is config.yaml in this folder.
#           This block reads it via a 1-shot Python helper that emits
#           shell exports, then `eval`s them. Don't edit this block —
#           edit config.yaml.
# =====================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_YAML="$SCRIPT_DIR/config.yaml"

[[ -f "$CONFIG_YAML" ]] || { echo "ERROR: config.yaml not found at $CONFIG_YAML" >&2; exit 1; }

# Parse config.yaml -> shell exports. Quote values to survive whitespace/special chars.
eval "$(python3 - "$CONFIG_YAML" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)
for k, v in cfg.items():
    # Shell-safe single-quote the value (escape single quotes inside it)
    safe = str(v).replace("'", "'\\''")
    print(f"CFG_{k.upper()}='{safe}'")
PYEOF
)"

# Quick sanity check — must have the critical keys
for required in CFG_PROJECT_NAME CFG_STACK_NAME CFG_AWS_REGION; do
  if [[ -z "${!required:-}" ]]; then
    echo "ERROR: config.yaml is missing required key '${required#CFG_}' (lowercase in YAML)" >&2
    exit 1
  fi
done

# Convenience aliases for the rest of the script
PROJECT_NAME="$CFG_PROJECT_NAME"
STACK_NAME="$CFG_STACK_NAME"
AWS_REGION="$CFG_AWS_REGION"
EC2_TYPE="$CFG_EC2_INSTANCE_TYPE"
BOOTSTRAP_TIMEOUT="${CFG_BOOTSTRAP_TIMEOUT_SEC:-900}"
PEM_FILE="${PROJECT_NAME}-key.pem"

# CSVs live in ./data/ — hardcoded relative to this script's directory.
# Students MUST place the 7 Truck Delay CSVs in AWS_setup/data/ before running.
# See data/DATA_README.md for the required file list.
CSV_SOURCE_DIR="$SCRIPT_DIR/data"

# =====================================================================
#  HELPERS
# =====================================================================
# Colors only if stdout is a TTY (so logs to file stay clean)
if [[ -t 1 ]]; then
  C_BLUE=$'\033[1;36m'; C_GREEN=$'\033[1;32m'; C_RED=$'\033[1;31m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
  C_BLUE=""; C_GREEN=""; C_RED=""; C_DIM=""; C_RESET=""
fi

say()  { echo; echo "${C_BLUE}==> $*${C_RESET}"; }
ok()   { echo "${C_GREEN}✔ $*${C_RESET}"; }
note() { echo "${C_DIM}  $*${C_RESET}"; }
die()  { echo; echo "${C_RED}✖ $*${C_RESET}" >&2; exit 1; }

get_output() {
  # Read one stack output by key name
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

# =====================================================================
#  STEP 0 — Verify prerequisites
# =====================================================================
say "Step 0/7 — Verifying AWS CLI and credentials"
command -v aws >/dev/null 2>&1 || die "AWS CLI not installed. Install from https://aws.amazon.com/cli/"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || die "AWS credentials not configured. Run 'aws configure'."
ARN=$(aws sts get-caller-identity --query Arn --output text)
ok "AWS account $ACCOUNT_ID — $ARN"
note "Region:          $AWS_REGION"
note "Stack:           $STACK_NAME"
note "Project prefix:  $PROJECT_NAME"
note "EC2 type:        $EC2_TYPE"

if [[ "$PROJECT_NAME" == "mlops-m3-batch-2026" ]]; then
  echo
  echo "${C_RED}⚠  project_name in config.yaml is still the default ('mlops-m3-batch-2026').${C_RESET}"
  echo "   If another learner used the same name, S3 bucket creation will fail."
  echo "   Edit config.yaml before deploying."
  read -r -p "Continue anyway? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || die "Aborted by user."
fi

# ---- PREFLIGHT: data folder must contain the 7 expected CSVs ----
# We check this NOW (before any AWS resource creation) so a missing data folder
# never wastes 5 minutes of CloudFormation deploy. If this fails, fix the data
# folder and just re-run this script — nothing has been provisioned yet.
EXPECTED_CSVS=(
  truck_schedule_table.csv
  trucks_table.csv
  drivers_table.csv
  routes_table.csv
  traffic_table.csv
  city_weather.csv
  routes_weather.csv
)

if [[ ! -d "$CSV_SOURCE_DIR" ]]; then
  die "Data folder not found: $CSV_SOURCE_DIR
        Create AWS_setup/data/ and place the 7 Truck Delay CSVs there.
        See data/DATA_README.md for the file list."
fi

MISSING=()
for csv in "${EXPECTED_CSVS[@]}"; do
  [[ -f "$CSV_SOURCE_DIR/$csv" ]] || MISSING+=("$csv")
done

if (( ${#MISSING[@]} > 0 )); then
  echo
  echo "${C_RED}✖ Missing CSV(s) in $CSV_SOURCE_DIR:${C_RESET}"
  for f in "${MISSING[@]}"; do echo "    - $f"; done
  die "Place the missing file(s) in the data folder and re-run this script.
        See data/DATA_README.md for the file list and where to find them.
        (No AWS resources have been created yet — this is a free, instant retry.)"
fi
ok "Found all 7 Truck Delay CSVs in $CSV_SOURCE_DIR"

# Check for stuck stack from a previous failed run
EXISTING_STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "NONE")
if [[ "$EXISTING_STATUS" == "ROLLBACK_COMPLETE" ]]; then
  echo
  echo "${C_RED}Existing stack '$STACK_NAME' is in ROLLBACK_COMPLETE — can't update, must delete.${C_RESET}"
  read -r -p "Delete the broken stack now and recreate? [y/N] " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$AWS_REGION"
    aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"
    ok "Old stack deleted"
  else
    die "Aborted by user."
  fi
fi

# =====================================================================
#  STEP 1 — Deploy CloudFormation stack
# =====================================================================

# Resolve the latest Ubuntu 24.04 LTS AMI for the chosen region. Canonical
# (AWS owner ID 099720109477) is the official publisher. We filter by the
# 'ubuntu-noble-24.04-amd64-server-*' name pattern (Noble Numbat = 24.04 LTS),
# sort by CreationDate, and pick the newest.
say "Resolving latest Ubuntu 24.04 LTS AMI in $AWS_REGION ..."
LATEST_UBUNTU_AMI=$(aws ec2 describe-images \
    --region "$AWS_REGION" \
    --owners 099720109477 \
    --filters \
        "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
        "Name=state,Values=available" \
        "Name=architecture,Values=x86_64" \
    --query "sort_by(Images, &CreationDate) | [-1].ImageId" \
    --output text)

if [[ -z "$LATEST_UBUNTU_AMI" || "$LATEST_UBUNTU_AMI" == "None" ]]; then
  die "Could not resolve Ubuntu 24.04 LTS AMI in $AWS_REGION.
        Canonical may not publish 24.04 in this region yet.
        Try a different region or pin LatestUbuntuAmiId in m3_setup.yaml."
fi
ok "Ubuntu 24.04 LTS AMI: $LATEST_UBUNTU_AMI"

say "Step 1/7 — Deploying CloudFormation stack '$STACK_NAME' (~5 min)"
# Pass ALL parameters from config.yaml to CloudFormation. LatestUbuntuAmiId is
# auto-resolved above (NOT in config.yaml — it's region-specific and time-sensitive,
# so re-resolving per deploy is the right behaviour).
aws cloudformation deploy \
  --template-file m3_setup.yaml \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    ProjectName="$CFG_PROJECT_NAME" \
    AllowedSshCidr="${CFG_ALLOWED_SSH_CIDR:-0.0.0.0/0}" \
    Ec2InstanceType="$CFG_EC2_INSTANCE_TYPE" \
    Ec2VolumeSize="${CFG_EC2_VOLUME_SIZE_GB:-20}" \
    LatestUbuntuAmiId="$LATEST_UBUNTU_AMI" \
    RdsInstanceClass="$CFG_RDS_INSTANCE_CLASS" \
    RdsAllocatedStorage="${CFG_RDS_ALLOCATED_STORAGE_GB:-20}" \
    RdsEngineVersion="$CFG_RDS_ENGINE_VERSION" \
    RdsDatabaseName="$CFG_RDS_DATABASE_NAME" \
    RdsMasterUsername="$CFG_RDS_MASTER_USERNAME" \
    AlertEmail="${CFG_ALERT_EMAIL:-}" \
    BillingAlertThresholdUsd="${CFG_BILLING_ALERT_THRESHOLD_USD:-10}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION"
ok "Stack deployed"

# =====================================================================
#  STEP 2 — Read stack outputs
# =====================================================================
say "Step 2/7 — Reading stack outputs"
EC2_IP=$(get_output Ec2PublicIp)
EC2_DNS=$(get_output Ec2PublicDns)
S3_BUCKET=$(get_output S3BucketName)
SSM_PATH=$(get_output Ec2KeyPairSsmPath)
RDS_HOST=$(get_output RdsEndpoint)
SECRET_ARN=$(get_output RdsMasterPasswordSecretArn)
MLFLOW_URL=$(get_output MlflowUiUrl)
SAGEMAKER_ROLE=$(get_output SageMakerRoleArn)

ok "Outputs captured"
note "EC2 public IP:  $EC2_IP"
note "RDS endpoint:   $RDS_HOST"
note "S3 bucket:      $S3_BUCKET"
note "MLflow URL:     $MLFLOW_URL"

# =====================================================================
#  STEP 3 — Download EC2 private key from SSM
# =====================================================================
say "Step 3/7 — Downloading EC2 private key → $PEM_FILE"
if [[ -f "$PEM_FILE" ]] && [[ -s "$PEM_FILE" ]]; then
  ok "$PEM_FILE already exists, skipping (delete it manually if you want a fresh copy)"
else
  aws ssm get-parameter \
    --name "$SSM_PATH" \
    --with-decryption \
    --region "$AWS_REGION" \
    --query Parameter.Value \
    --output text > "$PEM_FILE"

  # On Git Bash, chmod 400 works. On native Windows it's a no-op (icacls covers it).
  chmod 400 "$PEM_FILE" 2>/dev/null || true
  ok ".pem downloaded and locked (chmod 400)"
fi

# =====================================================================
#  STEP 4 — Upload Truck Delay CSVs to S3
# =====================================================================
say "Step 4/7 — Uploading 7 Truck Delay CSVs to s3://$S3_BUCKET/data/raw/"
# Data folder already validated in Step 0 (all 7 CSVs present).
# `aws s3 sync` is idempotent — it skips files already in S3 with matching size/mtime.
aws s3 sync "$CSV_SOURCE_DIR" "s3://$S3_BUCKET/data/raw/" --region "$AWS_REGION" --exclude "*.md"
ok "CSVs synced to S3"

# =====================================================================
#  STEP 5 — Wait for EC2 bootstrap to complete (poll MLflow UI)
# =====================================================================
say "Step 5/7 — Waiting for EC2 bootstrap (polling MLflow at $MLFLOW_URL)"
note "Bootstrap installs Python 3.12 + Docker + AWS CLI + MLflow."
note "Typical: 3-8 min on the default t3.medium."
note "Timeout: ${BOOTSTRAP_TIMEOUT}s. If exceeded, SSH in and check /var/log/m3-bootstrap.log."

START_TS=$(date +%s)
ATTEMPTS=0
while true; do
  if curl -s -o /dev/null -m 5 "http://${EC2_IP}:5000"; then
    echo
    ok "MLflow UI is up"
    break
  fi
  ELAPSED=$(( $(date +%s) - START_TS ))
  if (( ELAPSED > BOOTSTRAP_TIMEOUT )); then
    echo
    die "Bootstrap did not finish after ${BOOTSTRAP_TIMEOUT}s.
        SSH in to diagnose:
          ssh -i $PEM_FILE ubuntu@$EC2_DNS
          tail -50 /var/log/m3-bootstrap.log
        If you overrode EC2_TYPE to t3.micro, the cause is almost certainly OOM
        during pip install of MLflow. Fix: destroy stack, redeploy with the
        default EC2_TYPE=t3.medium."
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  printf "  ... %ds elapsed (attempt %d)\r" "$ELAPSED" "$ATTEMPTS"
  sleep 20
done

# =====================================================================
#  STEP 6 — SCP load_csvs.py to EC2, then SSH and run it
# =====================================================================
say "Step 6/7 — Copying load_csvs.py to EC2 and loading CSVs into RDS (~3-5 min)"

LOADER_LOCAL="$(dirname "$0")/load_csvs.py"
[[ -f "$LOADER_LOCAL" ]] || die "load_csvs.py not found next to this script: $LOADER_LOCAL"

# Common SSH/SCP flags. StrictHostKeyChecking=no is safe here because the EC2
# instance is fresh and the IP/DNS came from a trusted CloudFormation output.
SSH_FLAGS=(-i "$PEM_FILE"
           -o StrictHostKeyChecking=no
           -o UserKnownHostsFile=/dev/null
           -o ConnectTimeout=30)

# /opt/m3 was created by EC2 UserData (root-owned), so we stage in ~ubuntu first
# and then sudo-move into place — avoids a separate `chmod` round-trip.
scp "${SSH_FLAGS[@]}" "$LOADER_LOCAL" ubuntu@"$EC2_DNS":/home/ubuntu/load_csvs.py
ssh "${SSH_FLAGS[@]}" ubuntu@"$EC2_DNS" \
    "sudo mv /home/ubuntu/load_csvs.py /opt/m3/load_csvs.py && \
     sudo chown ubuntu:ubuntu /opt/m3/load_csvs.py && \
     python3 /opt/m3/load_csvs.py"
ok "All 7 tables loaded into truck_delay_db"

# =====================================================================
#  STEP 7 — Final summary
# =====================================================================
say "Step 7/7 — Module 3 environment is ready"
TOTAL_ELAPSED=$(( $(date +%s) - START_TS ))
cat <<EOF

  ${C_GREEN}════════════════════════════════════════════════════════════════${C_RESET}
  ${C_GREEN}  ✔ Deployment complete${C_RESET}
  ${C_GREEN}════════════════════════════════════════════════════════════════${C_RESET}

  Stack name:       $STACK_NAME
  AWS region:       $AWS_REGION
  Bootstrap time:   ${TOTAL_ELAPSED}s

  ── Endpoints ──
  MLflow UI:        $MLFLOW_URL
  EC2 SSH:          ssh -i $PEM_FILE ubuntu@$EC2_DNS
  RDS endpoint:     $RDS_HOST (port 5432)
  RDS database:     truck_delay_db
  RDS user:         mlops_admin
  RDS password:     aws secretsmanager get-secret-value --secret-id $SECRET_ARN --region $AWS_REGION --query SecretString --output text | python -c "import json,sys; print(json.load(sys.stdin)['password'])"
  S3 bucket:        s3://$S3_BUCKET
  SageMaker role:   $SAGEMAKER_ROLE

  ── Next steps ──
  1. Open MLflow UI in browser to confirm:  $MLFLOW_URL
  2. Create a SageMaker Notebook Instance (Console → SageMaker AI → Notebooks)
     - IAM role: paste the SageMaker role ARN above
     - VPC: ${PROJECT_NAME}-vpc, subnet ${PROJECT_NAME}-public-a
  3. Upload Lab C / Lab D notebooks and start work.

  ── At end of session: DESTROY EVERYTHING ──
    aws cloudformation delete-stack --stack-name $STACK_NAME --region $AWS_REGION
    rm -f $PEM_FILE

EOF
