# Module 3 — Manual Testing & Troubleshooting Reference (RDS + S3 + EC2)

> **What this is:** a reference doc for **verifying** the AWS environment that `deploy_m3.sh` created, and **troubleshooting** when something doesn't behave.
>
> **What this is NOT:** a hands-on provisioning lab. Everything is already provisioned by `m3_setup.yaml` + `load_csvs.py` + `deploy_m3.sh`. Use this doc to confirm that's true, or to debug.

---

## The quick way: 3 verification scripts

Run these in order. Each prints a clear OK / FAIL line and exits 0 on success.

| Script | Where to run | What it checks |
|---|---|---|
| `verify_ec2.py` | Your **laptop** | EC2 is running, both AWS health checks green, SSH port open, MLflow UI returns HTTP 200 |
| `verify_s3.py` | Your **laptop** | S3 bucket exists, all 7 Truck Delay CSVs at `data/raw/` with non-zero sizes |
| `verify_rds.py` | **On the EC2 instance** (RDS is private) | DB connection works, all 7 tables exist with expected row counts, sample SELECT + sample JOIN return real rows |

**Run from laptop:**
```bash
cd Module\ 3/AWS_setup/
python verify_ec2.py
python verify_s3.py
```

**Run on EC2 (for the RDS one):**
```bash
EC2_DNS=$(aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
    --query "Stacks[0].Outputs[?OutputKey=='Ec2PublicDns'].OutputValue" --output text)

scp -i mlops-m3-batch-2026-key.pem verify_rds.py ubuntu@$EC2_DNS:~/
ssh -i mlops-m3-batch-2026-key.pem ubuntu@$EC2_DNS "python3 verify_rds.py"
```

If all three exit 0, your Module 3 environment is fully ready for Labs C / D / E.

> Stack name or region different? Set env vars before running:
> ```bash
> STACK_NAME=m3-priya AWS_REGION=us-east-1 python verify_s3.py
> ```

---

## Doing it manually instead (good for understanding what the scripts check)

If you want to learn what's happening or do ad-hoc poking around, the rest of this doc shows the same checks as raw `aws` / `psql` / `psycopg2` snippets.

## Getting credentials

Before you can run any of the snippets in this doc, fetch the RDS connection details from CloudFormation outputs and Secrets Manager.

```bash
# From AWS_setup/ folder
STACK_NAME=m3-stack
REGION=ap-south-1

RDS_HOST=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION \
    --query "Stacks[0].Outputs[?OutputKey=='RdsEndpoint'].OutputValue" --output text)

SECRET_ARN=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION \
    --query "Stacks[0].Outputs[?OutputKey=='RdsMasterPasswordSecretArn'].OutputValue" --output text)

RDS_PASSWORD=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --region $REGION \
    --query SecretString --output text | python -c "import json,sys; print(json.load(sys.stdin)['password'])")

echo "Host: $RDS_HOST"
echo "User: mlops_admin"
echo "DB:   truck_delay_db"
echo "Pass: $RDS_PASSWORD"   # treat as sensitive — don't paste into chat
```

The same values are written to `/opt/m3/config.json` on the EC2 instance by CloudFormation UserData. From an SSH session on EC2 you can just `cat /opt/m3/config.json`.

---

## Connection test (5-line sanity check)

Use this when RDS connection fails and you want to isolate "is my network/cred set up right?" from "is the loader script broken?". Run on the EC2 instance:

```python
"""Quick connectivity test — RDS PostgreSQL."""
import json
import psycopg2

with open("/opt/m3/config.json") as f:
    cfg = json.load(f)

conn = psycopg2.connect(
    host=cfg["rds_host"], port=cfg["rds_port"], dbname=cfg["rds_db"],
    user=cfg["rds_user"], password=cfg["rds_password"],
)
cur = conn.cursor()
cur.execute("SELECT version();")
print("Connected to:", cur.fetchone()[0])
cur.close()
conn.close()
```

Expected output:
```
Connected to: PostgreSQL 15.10 on x86_64-pc-linux-gnu, compiled by gcc ...
```

If you get **"Connection timed out"**, jump to the Troubleshooting section.

---

## Verify the data (row counts + sample query)

After `load_csvs.py` finishes, run this on EC2 to confirm everything loaded correctly and you can run a real query:

```python
"""Verify row counts and run a sample join."""
import json
import psycopg2

with open("/opt/m3/config.json") as f:
    cfg = json.load(f)

EXPECTED_COUNTS = {
    "truck_schedule_table": 12_308,
    "trucks_table": 1_301,
    "drivers_table": 1_301,
    "routes_table": 2_353,
    "traffic_table": 2_597_914,
    "city_weather": 55_177,
    "routes_weather": 425_713,
}

conn = psycopg2.connect(
    host=cfg["rds_host"], port=cfg["rds_port"], dbname=cfg["rds_db"],
    user=cfg["rds_user"], password=cfg["rds_password"],
)
cur = conn.cursor()

print("=" * 55)
print(f"{'Table':<30} {'Actual':>10} {'Expected':>10}")
print("=" * 55)
all_ok = True
for table, expected in EXPECTED_COUNTS.items():
    cur.execute(f"SELECT COUNT(*) FROM {table};")
    actual = cur.fetchone()[0]
    status = "OK" if actual == expected else "MISMATCH"
    if status == "MISMATCH":
        all_ok = False
    print(f"{table:<30} {actual:>10,} {expected:>10,}  {status}")
print("=" * 55)

# Sample join: schedule + truck details
print("\nSample join (schedule + trucks):")
cur.execute("""
    SELECT s.truck_id, t.fuel_type, t.truck_age, s.delay
    FROM truck_schedule_table s
    JOIN trucks_table t ON s.truck_id = t.truck_id
    LIMIT 5;
""")
for row in cur.fetchall():
    print(f"  truck={row[0]}, fuel={row[1]}, age={row[2]}, delay={row[3]}")

cur.close()
conn.close()

print("\nAll row counts match." if all_ok else "\nWARNING: Some counts do not match.")
```

Expected output:
```
=======================================================
Table                             Actual   Expected
=======================================================
truck_schedule_table              12,308     12,308  OK
trucks_table                       1,301      1,301  OK
drivers_table                      1,301      1,301  OK
routes_table                       2,353      2,353  OK
traffic_table                  2,597,914  2,597,914  OK
city_weather                      55,177     55,177  OK
routes_weather                   425,713    425,713  OK
=======================================================

Sample join (schedule + trucks):
  truck=101, fuel=Diesel, age=3, delay=0
  ...

All row counts match.
```

---

## Inspecting data with `psql` (CLI alternative)

For ad-hoc queries without writing Python, use the `psql` client (already installed on EC2 by UserData):

```bash
# From an SSH session on EC2
PGPASSWORD="$(cat /opt/m3/config.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["rds_password"])')"
psql -h "$(cat /opt/m3/config.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["rds_host"])')" \
     -U mlops_admin -d truck_delay_db
```

Useful interactive commands:
```
\dt                              -- list all tables
\d truck_schedule_table          -- describe one table's schema
SELECT COUNT(*) FROM trucks_table;
SELECT DISTINCT fuel_type FROM trucks_table;
\q                               -- quit
```

---

## Troubleshooting

### "Connection timed out" when connecting to RDS

Work through this checklist in order:

1. **Same VPC**: Confirm the EC2 and RDS instances share a VPC. (CloudFormation puts them in the same VPC by design — only relevant if you're connecting from a different machine.)
2. **Same region**: Both must be in the same AWS region (e.g., `ap-south-1`). Cross-region connections require additional networking.
3. **Security group rule**: The RDS security group must allow inbound 5432 **from the EC2 security group** (not a CIDR). CloudFormation sets this up — if you modified it manually, double-check.
4. **RDS status**: In the AWS Console, RDS dashboard must show **Available**, not **Creating** / **Modifying** / **Backing up**.
5. **Port**: 5432 (PostgreSQL), not 3306 (MySQL).
6. **Endpoint freshness**: If you destroyed and redeployed the stack, the RDS endpoint changes. Re-fetch it from CloudFormation outputs.

### Slow data loading (`traffic_table` takes 10+ minutes)

`load_csvs.py` uses PostgreSQL's `COPY` command, which is the fastest method (~30-60 sec on `db.t3.small` for 2.6M rows). If it's much slower:

- **RDS instance class**: `db.t3.micro` (1 GB RAM) chokes on the 2.6M-row COPY. Upgrade to `db.t3.small` (the default) or higher.
- **EC2-to-RDS latency**: They should be in the same Availability Zone for lowest latency. CloudFormation puts both in the same VPC, but RDS may pick a different AZ — usually fine, but worth checking if loading is very slow.
- **CSV in S3**: The CSV is streamed from S3 through the EC2 to RDS. A slow EC2 (t3.micro) bottlenecks this; the default `t3.medium` is fine.

### "No such file: /opt/m3/config.json"

UserData hasn't finished yet, or the EC2 instance was created with a different stack and you're SSHing into the wrong one. Check `ls /var/log/m3-bootstrap-complete` — if missing, UserData is still running. Tail `/var/log/m3-bootstrap.log` to see what step it's on.

### "psycopg2 not found"

`psycopg2-binary` is installed by UserData. If you see this error, you're likely either:
- Using a different Python interpreter than the system one (check `which python3`)
- Bootstrap didn't complete cleanly — re-check `/var/log/m3-bootstrap.log`

Fix: `pip3 install --user psycopg2-binary`

### "FATAL: database truck_delay_db does not exist"

This shouldn't happen — CloudFormation creates the database via the `DBName` parameter on the RDS resource. If you see this, your stack's `RdsDatabaseName` parameter was overridden to a different value. Check stack parameters:
```bash
aws cloudformation describe-stacks --stack-name m3-stack --region ap-south-1 \
    --query "Stacks[0].Parameters[?ParameterKey=='RdsDatabaseName']"
```

### S3 access denied during sync

The IAM identity running `aws s3 sync` (your local CLI user) needs `s3:PutObject` on the bucket. If you have `AdministratorAccess` this is automatic. If you scoped permissions, attach `AmazonS3FullAccess` or a bucket-specific policy.

The **EC2 instance itself** uses an instance profile created by CloudFormation and has S3 read access to the bucket — that's separate from your local CLI.

---

## When to use this doc vs the README

- **`AWS_SETUP_README.md`** — read first; walks you through deployment end-to-end
- **`verify_ec2.py` / `verify_s3.py` / `verify_rds.py`** — fastest way to confirm everything is healthy
- **`MANUAL_TESTING_REFERENCE.md`** (this file) — when you need to understand what the verify scripts are checking, or to do ad-hoc inspection
- **`data/DATA_README.md`** — what CSVs need to be in `data/` before deployment
