#!/usr/bin/env bash
# M3 Lab E (Deployment using Streamlit) -- launcher meant to run ON the EC2.
# Pulls DB creds from /opt/m3/config.json, sets env vars, kicks off streamlit
# in the background. Lab E auto-picks the best available model bundle:
# Lab D tuned (if it beat the baseline) -> Lab C XGBoost -> heuristic.
set -euo pipefail

CFG=/opt/m3/config.json
export DB_HOST="$(python3 -c "import json; print(json.load(open('$CFG'))['rds_host'])")"
export DB_USER="$(python3 -c "import json; print(json.load(open('$CFG'))['rds_user'])")"
export DB_NAME="$(python3 -c "import json; print(json.load(open('$CFG'))['rds_db'])")"
export DB_PASSWORD="$(python3 -c "import json; print(json.load(open('$CFG'))['rds_password'])")"
export S3_BUCKET="$(python3 -c "import json; print(json.load(open('$CFG'))['s3_bucket'])")"
export MLFLOW_TRACKING_URI="http://localhost:5000"
export DEMO_MODE=false

cd /home/ubuntu

# Kill any old streamlit process
pkill -f "streamlit run app.py" 2>/dev/null || true
sleep 2

# Launch streamlit detached
nohup /home/ubuntu/streamlit-venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    > /home/ubuntu/streamlit.log 2>&1 &

echo "Launched streamlit (PID $!). Waiting for health check ..."
for i in $(seq 1 20); do
  if curl -sf -o /dev/null http://localhost:8501/_stcore/health 2>/dev/null; then
    echo "  streamlit is up after ${i}s"
    exit 0
  fi
  sleep 1
done
echo "  streamlit did NOT respond after 20s — tail of streamlit.log:"
tail -20 /home/ubuntu/streamlit.log
exit 1
