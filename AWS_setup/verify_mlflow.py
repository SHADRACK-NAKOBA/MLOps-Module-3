"""Verify the MLflow tracking server on the EC2 is healthy + usable from outside.

Run this LOCALLY (your laptop). Reads stack_name + aws_region from config.yaml.

WHAT IT CHECKS (4 layers, in order of "useful evidence the service is working"):
    1. TCP port 5000 is reachable from your laptop
    2. HTTP GET / returns real HTML (proves the MLflow allowed-hosts middleware
       is configured correctly — without --allowed-hosts '*', MLflow 3.x rejects
       non-localhost requests with HTTP 403)
    3. MLflow REST API responds to a search-experiments call with valid JSON
    4. End-to-end: use the Python mlflow client to create an experiment, log a
       parameter and metric, retrieve the run, then delete it as cleanup

Usage:
    python verify_mlflow.py

Exits 0 on full pass, non-zero on any failure (suitable for CI / shell pipelines).
"""

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3
import yaml

# MLflow prints unicode emojis (🏃, 🧪) when starting runs. On Windows
# default consoles (cp1252) those raise UnicodeEncodeError. Reconfigure
# stdout to be UTF-8 forgiving so we don't fail Check 4 for a cosmetic reason.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass  # older Python or non-TTY — best-effort

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
with open(CONFIG_PATH) as _f:
    _cfg = yaml.safe_load(_f)
STACK_NAME = _cfg["stack_name"]
AWS_REGION = _cfg["aws_region"]

TEST_EXPERIMENT_NAME = "_verify_mlflow_smoketest"

TALLY = {"pass": 0, "fail": 0}


def check(name, ok, detail=""):
    label = "[ OK ]" if ok else "[FAIL]"
    line = f"{label}   {name}"
    if detail:
        line += f"\n        {detail}"
    print(line)
    TALLY["pass" if ok else "fail"] += 1


def get_stack_outputs():
    cf = boto3.client("cloudformation", region_name=AWS_REGION)
    outs = cf.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in outs}


def check_tcp(host, port, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def http_get(url, timeout=10):
    """Return (status_code, body_first_500_chars). On error returns (None, error_msg)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(500).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except (urllib.error.URLError, socket.timeout) as e:
        return None, str(e)


def main():
    outputs = get_stack_outputs()
    ec2_ip = outputs.get("Ec2PublicIp")
    mlflow_url = outputs.get("MlflowUiUrl")
    if not ec2_ip or not mlflow_url:
        print("FAIL: Could not read Ec2PublicIp / MlflowUiUrl from stack outputs.")
        sys.exit(1)

    mlflow_url = mlflow_url.rstrip("/")
    print(f"EC2 public IP: {ec2_ip}")
    print(f"MLflow URL:    {mlflow_url}\n")

    # ── Check 1: TCP reachability ──────────────────────────────────────
    print("Check 1: TCP port 5000 reachable from your laptop")
    tcp_ok = check_tcp(ec2_ip, 5000)
    check("TCP 5000 open", tcp_ok, f"target {ec2_ip}:5000")
    if not tcp_ok:
        print("\n        HINT: connection refused or timed out. Likely causes:")
        print("        - EC2 instance is stopped or terminated")
        print("        - Security group doesn't allow 5000 from your IP")
        print("        - MLflow systemd service isn't running on EC2")
        sys.exit(1)
    print()

    # ── Check 2: HTTP returns HTML ─────────────────────────────────────
    print(f"Check 2: HTTP GET {mlflow_url}/ returns real MLflow HTML")
    code, body = http_get(mlflow_url + "/")
    is_html = code is not None and 200 <= code < 400 and "<html" in body.lower()
    is_mlflow = "mlflow" in body.lower()
    check(
        "HTML served (allowed-hosts middleware accepts external clients)",
        is_html and is_mlflow,
        f"HTTP {code}" + ("" if is_html else f" — body excerpt: {body[:120]!r}"),
    )
    if code == 403:
        print("        HINT: HTTP 403 = MLflow 3.x host-header rejection.")
        print("        The systemd unit must launch mlflow server with")
        print("        --allowed-hosts '*' (or specific hosts).")
        print("        Check /etc/systemd/system/mlflow.service on the EC2.")
    print()

    # ── Check 3: MLflow REST API ───────────────────────────────────────
    api_url = mlflow_url + "/api/2.0/mlflow/experiments/search"
    print(f"Check 3: MLflow REST API at {api_url}")
    req = urllib.request.Request(
        api_url,
        data=b'{"max_results": 5}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        api_ok = "experiments" in data or "next_page_token" in data
        n_exps = len(data.get("experiments", []))
        check(
            "REST API responds with valid JSON",
            api_ok,
            f"found {n_exps} experiments via search-experiments",
        )
    except Exception as e:
        check("REST API responds with valid JSON", False,
              f"{type(e).__name__}: {e}")
    print()

    # ── Check 4: Python client end-to-end round trip ───────────────────
    print("Check 4: Python client end-to-end (create exp, log run, retrieve, cleanup)")
    try:
        import mlflow  # type: ignore
    except ImportError:
        check("Python client end-to-end", False,
              "mlflow not installed locally; `pip install mlflow` then re-run")
        _summary_and_exit()

    try:
        mlflow.set_tracking_uri(mlflow_url)

        # Use (or create) the smoketest experiment
        exp = mlflow.get_experiment_by_name(TEST_EXPERIMENT_NAME)
        if exp is None:
            exp_id = mlflow.create_experiment(TEST_EXPERIMENT_NAME)
        else:
            exp_id = exp.experiment_id
        mlflow.set_experiment(TEST_EXPERIMENT_NAME)

        # Log a uniquely-identifiable smoketest run
        smoketest_id = int(time.time())
        with mlflow.start_run(run_name=f"smoketest_{smoketest_id}") as run:
            mlflow.log_param("smoketest_id", smoketest_id)
            mlflow.log_metric("verify_metric", 1.0)
            run_id = run.info.run_id

        # Retrieve it by filter
        retrieved = mlflow.search_runs(
            experiment_ids=[exp_id],
            filter_string=f"params.smoketest_id = '{smoketest_id}'",
            max_results=1,
        )
        found = len(retrieved) > 0
        check(
            "Round-trip: log_param + log_metric persisted and retrievable",
            found,
            f"run_id={run_id}" if found else "newly-logged run not visible to search_runs",
        )

        # Cleanup: delete the smoketest run. Keep the experiment in case other
        # verifications are running concurrently or have leftover runs.
        if found:
            mlflow.delete_run(run_id)
    except Exception as e:
        check("Python client end-to-end", False,
              f"{type(e).__name__}: {e}")
    print()

    _summary_and_exit()


def _summary_and_exit():
    print(f"Summary: {TALLY['pass']} PASS, {TALLY['fail']} FAIL")
    sys.exit(0 if TALLY["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
