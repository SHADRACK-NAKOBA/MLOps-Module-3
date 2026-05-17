"""Verify the RDS database is up and the 7 Truck Delay tables are populated.

WHERE TO RUN: on the EC2 instance (RDS is private — not reachable from your
laptop). Quickest path:

    # From AWS_setup/ on your laptop:
    EC2_DNS=$(aws cloudformation describe-stacks --stack-name m3-stack \
        --region ap-south-1 \
        --query "Stacks[0].Outputs[?OutputKey=='Ec2PublicDns'].OutputValue" \
        --output text)
    scp -i mlops-m3-batch-2026-key.pem verify_rds.py ubuntu@$EC2_DNS:~/
    ssh -i mlops-m3-batch-2026-key.pem ubuntu@$EC2_DNS "python3 verify_rds.py"

WHAT IT CHECKS:
    1. psycopg2 connect succeeds + PostgreSQL version
    2. The 7 expected tables exist
    3. Each table's row count matches the expected reference value
    4. A sample SELECT on trucks_table returns 3 real rows
    5. A sample JOIN (schedule + trucks) returns 3 real rows
"""

import json
import sys

import psycopg2

CONFIG_PATH = "/opt/m3/config.json"

EXPECTED_ROW_COUNTS = {
    "truck_schedule_table": 12_308,
    "trucks_table": 1_300,
    "drivers_table": 1_300,
    "routes_table": 2_352,
    "traffic_table": 2_597_913,
    "city_weather": 55_176,
    "routes_weather": 425_712,
}


def main():
    print(f"Reading config from {CONFIG_PATH} ...")
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    print(f"Connecting to {cfg['rds_host']}:{cfg['rds_port']}/{cfg['rds_db']} as {cfg['rds_user']} ...")
    conn = psycopg2.connect(
        host=cfg["rds_host"],
        port=cfg["rds_port"],
        dbname=cfg["rds_db"],
        user=cfg["rds_user"],
        password=cfg["rds_password"],
        connect_timeout=15,
    )
    cur = conn.cursor()

    # 1. Version check
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"OK: Connected. {version.split(',')[0]}\n")

    # 2 + 3. List tables and verify row counts
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' ORDER BY tablename;
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables in 'public' schema ({len(tables)} found):")

    print(f"  {'Table':<30} {'Actual':>10} {'Expected':>10}   Status")
    print("  " + "-" * 60)
    failures = 0
    for table, expected in EXPECTED_ROW_COUNTS.items():
        if table not in tables:
            print(f"  {table:<30} {'-':>10} {expected:>10,}   MISSING")
            failures += 1
            continue
        cur.execute(f"SELECT COUNT(*) FROM {table};")
        actual = cur.fetchone()[0]
        status = "OK" if actual == expected else "MISMATCH"
        if status == "MISMATCH":
            failures += 1
        print(f"  {table:<30} {actual:>10,} {expected:>10,}   {status}")
    print()

    # 4. Sample rows from one table
    print("Sample rows from trucks_table (LIMIT 3):")
    cur.execute("SELECT truck_id, truck_age, fuel_type, mileage_mpg FROM trucks_table LIMIT 3;")
    for row in cur.fetchall():
        print(f"  truck_id={row[0]}, age={row[1]}, fuel={row[2]}, mileage_mpg={row[3]}")
    print()

    # 5. Sample join
    print("Sample join (truck_schedule_table + trucks_table, LIMIT 3):")
    cur.execute("""
        SELECT s.truck_id, t.fuel_type, t.truck_age, s.delay
        FROM truck_schedule_table s
        JOIN trucks_table t ON s.truck_id = t.truck_id
        LIMIT 3;
    """)
    for row in cur.fetchall():
        print(f"  truck_id={row[0]}, fuel={row[1]}, age={row[2]}, delay={row[3]}")
    print()

    cur.close()
    conn.close()

    if failures == 0:
        print("OK: All 7 tables present with expected row counts.")
        sys.exit(0)
    else:
        print(f"FAIL: {failures} table(s) missing or with wrong row count.")
        sys.exit(1)


if __name__ == "__main__":
    main()
