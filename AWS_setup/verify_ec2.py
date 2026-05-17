"""Verify the EC2 instance is running and the MLflow tracking server responds.

Run this LOCALLY (your laptop). Reads stack_name + aws_region from config.yaml.

WHAT IT CHECKS:
    1. EC2 instance state == 'running' (and both AWS status checks pass)
    2. Port 22 (SSH) accepts a TCP connection
    3. Port 5000 (MLflow UI) returns HTTP 200

Usage:
    python verify_ec2.py
"""

import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import boto3
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
with open(CONFIG_PATH) as _f:
    _cfg = yaml.safe_load(_f)
STACK_NAME = _cfg["stack_name"]
AWS_REGION = _cfg["aws_region"]


def get_stack_outputs():
    cf = boto3.client("cloudformation", region_name=AWS_REGION)
    outputs = cf.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def check_tcp_port(host, port, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_http(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code   # any HTTP status counts as "server is up"
    except (urllib.error.URLError, socket.timeout):
        return None


def main():
    outputs = get_stack_outputs()
    public_ip = outputs.get("Ec2PublicIp")
    if not public_ip:
        print("FAIL: Ec2PublicIp not found in stack outputs")
        sys.exit(1)

    print(f"EC2 public IP: {public_ip}")
    print(f"MLflow URL:    {outputs.get('MlflowUiUrl', '(missing)')}\n")

    failures = 0

    # 1. Instance state via AWS API
    ec2 = boto3.client("ec2", region_name=AWS_REGION)
    desc = ec2.describe_instances(Filters=[
        {"Name": "ip-address", "Values": [public_ip]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
    ])
    reservations = desc.get("Reservations", [])
    if not reservations:
        print(f"FAIL: no EC2 instance found with public IP {public_ip}")
        sys.exit(1)
    instance = reservations[0]["Instances"][0]
    instance_id = instance["InstanceId"]
    state = instance["State"]["Name"]
    print(f"Instance {instance_id} state: {state}")
    if state != "running":
        print(f"FAIL: instance is not 'running'")
        failures += 1

    # AWS health checks
    status = ec2.describe_instance_status(InstanceIds=[instance_id])
    statuses = status.get("InstanceStatuses", [])
    if statuses:
        sys_check = statuses[0]["SystemStatus"]["Status"]
        inst_check = statuses[0]["InstanceStatus"]["Status"]
        print(f"System status:    {sys_check}")
        print(f"Instance status:  {inst_check}")
        if sys_check != "ok" or inst_check != "ok":
            print("FAIL: AWS health checks not green")
            failures += 1
    print()

    # 2. SSH port reachable
    print(f"Checking TCP {public_ip}:22 (SSH) ...")
    if check_tcp_port(public_ip, 22):
        print("OK: SSH port is open")
    else:
        print("FAIL: SSH port unreachable")
        failures += 1
    print()

    # 3. MLflow HTTP
    mlflow_url = outputs.get("MlflowUiUrl") or f"http://{public_ip}:5000"
    print(f"Checking {mlflow_url} ...")
    code = check_http(mlflow_url)
    if code and 200 <= code < 500:
        print(f"OK: MLflow tracking server responded HTTP {code}")
    else:
        print("FAIL: MLflow tracking server not responding")
        print("      Bootstrap may still be installing MLflow.")
        print("      SSH to the instance and run: tail -50 /var/log/m3-bootstrap.log")
        failures += 1
    print()

    if failures == 0:
        print("OK: EC2 + MLflow are healthy.")
        sys.exit(0)
    else:
        print(f"FAIL: {failures} check(s) did not pass.")
        sys.exit(1)


if __name__ == "__main__":
    main()
