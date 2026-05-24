#!/usr/bin/env bash
# =============================================================================
#  M3 Lab E (Deployment using Streamlit) — Run dashboard against live RDS + S3
# =============================================================================
#  Loads model artifacts from S3 with three-tier priority (utils.load_artifacts):
#    1. Lab D tuned PyCaret pipeline (if it beat Lab C baseline)
#    2. Lab C XGBoost + encoder + scaler
#    3. Heuristic fallback (when neither is available)
# =============================================================================
#
#  USAGE
#    ./run_live.sh              # launches streamlit on port 8501
#    PORT=8502 ./run_live.sh    # override port
#
#  WHAT IT DOES
#    1. Reads stack outputs from CloudFormation (RDS endpoint, S3 bucket,
#       MLflow URL, Secrets Manager ARN for the RDS password).
#    2. Fetches the RDS master password from Secrets Manager.
#    3. Exports all the env vars that config.py expects.
#    4. Launches `streamlit run app.py` on port 8501.
#
#  REQUIREMENTS
#    - AWS CLI v2 (`aws sts get-caller-identity` must work)
#    - Stack 'm3-stack' must exist in ap-south-1 (or override STACK_NAME / AWS_REGION)
#    - Python env with streamlit + pandas + numpy + matplotlib + sqlalchemy
#      + psycopg2-binary + boto3 installed (see requirements.txt). The
#      "(mlops-pune-price)" conda env has these.
# =============================================================================

set -euo pipefail

STACK_NAME="${STACK_NAME:-m3-stack}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
PORT="${PORT:-8501}"

echo "==> Reading stack outputs from $STACK_NAME in $AWS_REGION ..."
get_output() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

DB_HOST="$(get_output RdsEndpoint)"
DB_PORT="$(get_output RdsPort)"
DB_NAME="$(get_output RdsDatabaseName)"
DB_USER="$(get_output RdsMasterUsername)"
SECRET_ARN="$(get_output RdsMasterPasswordSecretArn)"
S3_BUCKET="$(get_output S3BucketName)"
MLFLOW_URL="$(get_output MlflowUiUrl)"

for v in DB_HOST SECRET_ARN S3_BUCKET; do
  if [[ -z "${!v}" || "${!v}" == "None" ]]; then
    echo "ERROR: Could not read $v from stack outputs. Is $STACK_NAME deployed in $AWS_REGION?" >&2
    exit 1
  fi
done

echo "==> Fetching RDS master password from Secrets Manager ..."
DB_PASSWORD="$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_ARN" --region "$AWS_REGION" \
    --query SecretString --output text \
  | python -c 'import json,sys; print(json.load(sys.stdin)["password"])')"

if [[ -z "$DB_PASSWORD" ]]; then
  echo "ERROR: Empty password retrieved from Secrets Manager." >&2
  exit 1
fi

# IMPORTANT: RDS in this stack is private (PubliclyAccessible=False). Your
# laptop can only reach it if you have:
#   - Direct VPC access (e.g. via VPN / Direct Connect), OR
#   - An SSH tunnel through the EC2 instance:
#       ssh -i mlops-m3-batch-2026-key.pem -L 5432:<RDS_HOST>:5432 ubuntu@<EC2_DNS>
#     then set DB_HOST=localhost before running this script.
#
# If the connection times out, you're hitting that boundary. The simplest
# workaround for class is to run streamlit ON the EC2 itself (it can reach
# RDS via the EC2 SG): copy this folder up, install deps, and run there.

export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD S3_BUCKET
export MLFLOW_TRACKING_URI="$MLFLOW_URL"
export DEMO_MODE=false

echo "==> Environment ready"
echo "    DB_HOST              = $DB_HOST"
echo "    DB_USER              = $DB_USER"
echo "    DB_NAME              = $DB_NAME"
echo "    S3_BUCKET            = $S3_BUCKET"
echo "    MLFLOW_TRACKING_URI  = $MLFLOW_TRACKING_URI"
echo "    DEMO_MODE            = $DEMO_MODE"
echo ""
echo "==> Launching streamlit on http://localhost:$PORT ..."
streamlit run app.py --server.port "$PORT" --server.address localhost
