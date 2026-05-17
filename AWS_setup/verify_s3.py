"""Verify the S3 bucket exists and holds the 7 Truck Delay CSVs.

Run this LOCALLY (your laptop). Reads stack_name + aws_region from config.yaml.

Usage:
    python verify_s3.py
"""

import sys
from pathlib import Path

import boto3
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
with open(CONFIG_PATH) as _f:
    _cfg = yaml.safe_load(_f)
STACK_NAME = _cfg["stack_name"]
AWS_REGION = _cfg["aws_region"]

EXPECTED_CSVS = {
    "truck_schedule_table.csv",
    "trucks_table.csv",
    "drivers_table.csv",
    "routes_table.csv",
    "traffic_table.csv",
    "city_weather.csv",
    "routes_weather.csv",
}


def get_bucket_name():
    cf = boto3.client("cloudformation", region_name=AWS_REGION)
    outputs = cf.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    for out in outputs:
        if out["OutputKey"] == "S3BucketName":
            return out["OutputValue"]
    raise RuntimeError(f"S3BucketName not found in stack '{STACK_NAME}' outputs")


def main():
    bucket = get_bucket_name()
    print(f"Checking s3://{bucket}/data/raw/ ...\n")

    s3 = boto3.client("s3", region_name=AWS_REGION)
    response = s3.list_objects_v2(Bucket=bucket, Prefix="data/raw/")
    contents = response.get("Contents", [])
    keys_present = {obj["Key"].rsplit("/", 1)[-1] for obj in contents}

    missing = EXPECTED_CSVS - keys_present
    extra = keys_present - EXPECTED_CSVS

    # Per-file listing with size
    print(f"{'File':<30} {'Size':>10} {'Status':>8}")
    print("-" * 50)
    for csv in sorted(EXPECTED_CSVS):
        match = next((o for o in contents if o["Key"].endswith(csv)), None)
        if match:
            size_mb = match["Size"] / 1024 / 1024
            print(f"{csv:<30} {size_mb:>8.1f} MB    OK")
        else:
            print(f"{csv:<30} {'--':>10} {'MISSING':>8}")
    print()

    if missing:
        print(f"FAIL: missing {len(missing)} CSV(s): {sorted(missing)}")
        sys.exit(1)

    if extra:
        print(f"Note: extra non-CSV file(s) in folder: {sorted(extra)} (harmless)")

    print(f"OK: all 7 Truck Delay CSVs present in s3://{bucket}/data/raw/")


if __name__ == "__main__":
    main()
