"""Load 7 Truck Delay CSVs from S3 into RDS PostgreSQL.

Designed to run on the EC2 instance created by m3_setup.yaml.

WORKFLOW (orchestrated by deploy_m3.sh):
    1. CloudFormation creates EC2 + RDS + S3 + writes /opt/m3/config.json
       (config.json holds region, bucket, RDS host/port/db/user/password)
    2. deploy_m3.sh SCPs this file from local to /opt/m3/load_csvs.py on EC2
    3. deploy_m3.sh SSHes in and runs: python3 /opt/m3/load_csvs.py
    4. This script reads /opt/m3/config.json, then for each of the 7 tables:
       - DROP TABLE IF EXISTS (idempotent — safe to re-run)
       - CREATE TABLE with the schema below
       - Stream the CSV from S3 and bulk-load via Postgres COPY

REQUIREMENTS (installed by EC2 UserData):
    pip3 install psycopg2-binary boto3
"""

import io
import json

import boto3
import psycopg2

CONFIG_PATH = "/opt/m3/config.json"

# Schema for the 7 Truck Delay tables. Column order MUST match the CSV header order.
TABLES = {
    "truck_schedule_table": [
        "truck_id INT", "route_id VARCHAR(20)",
        "departure_date TIMESTAMP", "estimated_arrival TIMESTAMP", "delay INT",
    ],
    "trucks_table": [
        "truck_id INT", "truck_age INT", "load_capacity_pounds FLOAT",
        "mileage_mpg INT", "fuel_type VARCHAR(20)",
    ],
    "drivers_table": [
        "driver_id VARCHAR(20)", "name VARCHAR(50)", "gender VARCHAR(10)", "age INT",
        "experience INT", "driving_style VARCHAR(20)", "ratings INT",
        "vehicle_no INT", "average_speed_mph FLOAT",
    ],
    "routes_table": [
        "route_id VARCHAR(20)", "origin_id VARCHAR(20)", "destination_id VARCHAR(20)",
        "distance FLOAT", "average_hours FLOAT",
    ],
    "traffic_table": [
        "route_id VARCHAR(20)", "date DATE", "hour INT",
        "no_of_vehicles FLOAT", "accident INT",
    ],
    "city_weather": [
        "city_id VARCHAR(20)", "date DATE", "hour INT", "temp FLOAT",
        "wind_speed FLOAT", "description VARCHAR(50)", "precip FLOAT",
        "humidity FLOAT", "visibility FLOAT", "pressure FLOAT",
        "chanceofrain FLOAT", "chanceoffog FLOAT", "chanceofsnow FLOAT",
        "chanceofthunder FLOAT",
    ],
    "routes_weather": [
        "route_id VARCHAR(20)", "Date DATE", "temp FLOAT", "wind_speed FLOAT",
        "description VARCHAR(50)", "precip FLOAT", "humidity FLOAT",
        "visibility FLOAT", "pressure FLOAT", "chanceofrain FLOAT",
        "chanceoffog FLOAT", "chanceofsnow FLOAT", "chanceofthunder FLOAT",
    ],
}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_table(s3_client, cursor, table_name, columns, bucket):
    print(f"Loading {table_name}...", flush=True)
    cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    cursor.execute(f"CREATE TABLE {table_name} ({', '.join(columns)})")

    obj = s3_client.get_object(Bucket=bucket, Key=f"data/raw/{table_name}.csv")
    csv_data = obj["Body"].read().decode("utf-8")

    cursor.copy_expert(
        f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)",
        io.StringIO(csv_data),
    )
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]
    print(f"  -> {row_count:,} rows", flush=True)


def main():
    cfg = load_config()

    s3 = boto3.client("s3", region_name=cfg["region"])
    conn = psycopg2.connect(
        host=cfg["rds_host"],
        port=cfg["rds_port"],
        dbname=cfg["rds_db"],
        user=cfg["rds_user"],
        password=cfg["rds_password"],
    )
    conn.autocommit = True
    cur = conn.cursor()

    for table, cols in TABLES.items():
        load_table(s3, cur, table, cols, cfg["s3_bucket"])

    cur.close()
    conn.close()
    print("\nAll 7 tables loaded successfully.")


if __name__ == "__main__":
    main()
