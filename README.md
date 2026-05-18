# Module 3 — Student Manual

**First Cloud ML Development + Cloud Deployment** | 7 hours
 
> This document tells you **what you'll build, what data you'll work with, and what you'll learn** in Module 3. Read it before class. Refer to it when something feels confusing.

---

## What You'll Build in This Module

| Project | Domain | Type | Role in M3 |
|---------|--------|------|------------|
| **Real Estate Price Prediction** (carried over from M2) | Real Estate | Bridge | Deployed to AWS EC2 — you take last module's local app to the cloud (Lab A) |
| **Truck Delay Classification** | Logistics / Supply Chain | **Spine project** (M3 → M4 → M5 → M6 → M7 → M8) | The continuous project. M3 covers data infrastructure, EDA, model training, MLflow tracking, batch scoring, dashboarding (Labs B–E) |

The Truck Delay project is the **spine** — you will keep building on it for the next 5 modules. Module 3 is where this project begins.

---

## The Business Problem (Truck Delay Project)

**FreshBasket**, a grocery delivery company headquartered in Pune, runs a fleet of 1,300 trucks across 20+ Indian cities. Roughly **40% of their deliveries arrive late**. Late deliveries cause:

- Spoiled produce returns (₹15–20 lakhs/month loss)
- Customer churn (NPS dropping ~6 points per quarter)
- Driver overtime (drivers wait at warehouses for late trucks)

**Priya**, FreshBasket's MLOps lead, wants a predictive model that can **flag deliveries likely to be delayed BEFORE they leave the depot**, so the operations team can:
- Pre-warn customers
- Reroute risky shipments
- Schedule replacement trucks

Your job in Module 3: build the first cloud-deployed version of this model, with proper experiment tracking, feature engineering, and a dashboard the ops team can actually use.

---

## Module 3 Lab Roadmap

| # | Lab | Format | Duration | What You Do |
|---|-----|--------|----------|-------------|
| A | **EC2 Deploy — Real Estate API** | Tier 2 demo (instructor shows; you watch) | 30 min | Instructor demos how the M2 Real Estate FastAPI runs on a cloud EC2 instance. Bridge from M2 to M3. |
| B | **Spine Setup — RDS + S3** | Tier 2 demo (instructor shows; you watch) | 30 min | Instructor demos the pre-provisioned RDS PostgreSQL database (with 7 tables loaded) and the S3 bucket. |
| C | **EDA + Feature Engineering** | Tier 3 hands-on (you do it) | 90 min | Jupyter notebook. Connect to RDS, explore the 7 tables, engineer 36 features, save `final_features.csv` to S3. |
| D | **Model Training + MLflow** | Tier 3 hands-on (you do it) | 90 min | Train 3 models (Logistic Regression, Random Forest, XGBoost), log everything to MLflow on EC2, register the best model. |
| E | **Streamlit Dashboard + Batch Scoring** | Tier 3 hands-on (you do it) | 60 min | Build an interactive Streamlit dashboard for predictions; run a batch scoring script that writes results back to RDS. **Code distributed separately by instructor** — not in this repo while it stabilises. |

Labs A and B are **demonstrations only**. The AWS infrastructure has already been provisioned for you (using a CloudFormation template — your instructor will walk you through the YAML). You connect to it; you don't set it up.

Labs C, D, E are **hands-on**. This is where you spend most of class time, working in your own SageMaker notebook or local Jupyter.

---

## Learning Outcomes

By the end of Module 3, you will be able to:

### Cloud & Infrastructure
1. Connect to a remote EC2 instance over SSH
2. Read data from an AWS RDS PostgreSQL database in Python using `psycopg2` and `SQLAlchemy`
3. Upload and download files to/from AWS S3 using `boto3`
4. Open and use a SageMaker Notebook instance for cloud-based ML development
5. Understand the role of IAM execution roles when connecting AWS services
6. Read AWS CloudFormation YAML to understand what infrastructure was provisioned

### Data Engineering
7. Explore a multi-table relational dataset using SQL queries
8. Engineer features across 7 related tables using pandas + SQL
9. Apply pre-aggregation (avg/max over hourly data) before joining to avoid Cartesian explosions
10. Recognize and prevent data leakage when joining time-series tables

### Machine Learning
11. Train and evaluate three classification models — Logistic Regression, Random Forest, XGBoost — on the same dataset
12. Choose appropriate evaluation metrics for an imbalanced binary classification problem (Accuracy, Precision, Recall, F1, ROC-AUC)
13. Interpret feature importance for tree-based models

### MLOps Tools
14. Set up a connection to a self-hosted MLflow Tracking Server
15. Log parameters, metrics, and artifacts for each model training run
16. Compare runs side-by-side in the MLflow UI
17. Register a model in the MLflow Model Registry
18. Transition a registered model through stages (None → Staging → Production)

### Serving & Inference
19. Build an interactive Streamlit web app for ML predictions
20. Implement a batch scoring pipeline that writes predictions back to a database
21. Articulate when to use real-time inference vs. batch scoring

---

## The Truck Delay Dataset — Complete Reference

The dataset lives in an AWS RDS PostgreSQL database named **`truck_delay_db`**, pre-loaded with **7 tables** (~3 million rows total). The raw CSV files (~150 MB) are also in an S3 bucket at `s3://<bucket>/data/raw/`.

### Quick Summary

| Table | Rows | Granularity | Role |
|-------|-----:|------------|------|
| `truck_schedule_table` | 12,308 | One row per truck-route-day | **The fact table** — contains the target variable `delay` |
| `trucks_table` | 1,301 | One row per truck | Vehicle attributes (age, capacity, fuel type) |
| `drivers_table` | 1,301 | One row per driver-truck pair | Driver attributes (age, experience, style, rating) |
| `routes_table` | 2,353 | One row per route | Route metadata (origin, destination, distance) |
| `traffic_table` | 2,597,914 | One row per route-date-hour | Hourly traffic conditions on each route |
| `city_weather` | 55,177 | One row per city-date-hour | Hourly weather in each city |
| `routes_weather` | 425,713 | One row per route-date | Daily weather summary along each route |

### Target Variable

`truck_schedule_table.delay` — Binary integer (0 or 1):
- `0` = delivery arrived on time
- `1` = delivery was late

Class distribution: approximately **60% on-time, 40% delayed**. This is moderately imbalanced — accuracy alone is misleading; use F1 + ROC-AUC.

---

## Detailed Table Schemas

### Table 1: `truck_schedule_table` (12,308 rows) — **the target table**

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `truck_id` | INT | Unique truck identifier | 1042 |
| `route_id` | VARCHAR(20) | Route identifier (joins to `routes_table`) | "R_0789" |
| `departure_date` | TIMESTAMP | When the truck left the depot | 2019-01-15 06:00:00 |
| `estimated_arrival` | TIMESTAMP | Predicted arrival time | 2019-01-15 14:30:00 |
| `delay` | INT (0/1) | **TARGET** — was this delivery late? | 1 |

### Table 2: `trucks_table` (1,301 rows)

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `truck_id` | INT | Primary key (joins to `truck_schedule_table`) | 1042 |
| `truck_age` | INT | Truck age in years | 6 |
| `load_capacity_pounds` | FLOAT | Maximum load in pounds | 40000.0 |
| `mileage_mpg` | INT | Fuel efficiency (miles per gallon) | 7 |
| `fuel_type` | VARCHAR(20) | Diesel / Gas / etc. | "Diesel" |

### Table 3: `drivers_table` (1,301 rows)

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `driver_id` | INT | Primary key | 5021 |
| `name` | VARCHAR(50) | Driver name | "Rajesh K." |
| `gender` | VARCHAR(10) | Male / Female | "Male" |
| `age` | INT | Driver age | 38 |
| `experience` | INT | Years of driving experience | 12 |
| `driving_style` | VARCHAR(20) | Proactive / Conservative / Aggressive | "Proactive" |
| `ratings` | INT (1–5) | Customer rating | 4 |
| `vehicle_no` | INT | Truck assigned to this driver (joins to `trucks_table.truck_id`) | 1042 |
| `average_speed_mph` | FLOAT | Driver's historical avg speed | 58.3 |

> **Note:** `drivers_table.vehicle_no` is the foreign key to `trucks_table.truck_id`. Drivers and trucks have a 1:1 relationship in this dataset (1,301 of each).

### Table 4: `routes_table` (2,353 rows)

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `route_id` | VARCHAR(20) | Primary key (joins to `truck_schedule_table`, `traffic_table`, `routes_weather`) | "R_0789" |
| `origin_id` | VARCHAR(20) | Origin city ID (joins to `city_weather.city_id`) | "C_PUNE" |
| `destination_id` | VARCHAR(20) | Destination city ID (joins to `city_weather.city_id`) | "C_MUMBAI" |
| `distance` | FLOAT | Route distance in miles | 92.5 |
| `average_hours` | FLOAT | Expected travel time in hours | 2.5 |

### Table 5: `traffic_table` (2,597,914 rows)

The largest table. Hourly traffic measurements on each route.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `route_id` | VARCHAR(20) | Foreign key to `routes_table` | "R_0789" |
| `date` | DATE | Date of measurement | 2019-01-15 |
| `hour` | INT (0–23) | Hour of day | 7 |
| `no_of_vehicles` | INT | Vehicles counted that hour | 12450 |
| `accident` | INT (0/1) | Was there an accident on this route at this time? | 0 |

> **Important:** You will NOT join this directly to `truck_schedule_table` (12K rows × 2.6M rows = 31 billion row Cartesian explosion). You must **aggregate first** by `route_id` + `date`, computing avg vehicles and max accident, then join the aggregated result.

### Table 6: `city_weather` (55,177 rows)

Hourly weather for each city. Used twice in feature engineering — once for **origin city** weather, once for **destination city** weather.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `city_id` | VARCHAR(20) | City identifier (joins to `routes_table.origin_id` or `destination_id`) | "C_PUNE" |
| `date` | DATE | Date | 2019-01-15 |
| `hour` | INT (0–23) | Hour | 7 |
| `temp` | FLOAT | Temperature (°F) | 72.3 |
| `wind_speed` | FLOAT | Wind speed (mph) | 8.5 |
| `description` | VARCHAR(50) | Weather description | "Partly Cloudy" |
| `precip` | FLOAT | Precipitation (inches) | 0.0 |
| `humidity` | FLOAT | Humidity (%) | 65.0 |
| `visibility` | FLOAT | Visibility (miles) | 10.0 |
| `pressure` | FLOAT | Atmospheric pressure (millibars) | 1013.2 |
| `chanceofrain` | FLOAT | Probability of rain (%) | 12.0 |
| `chanceoffog` | FLOAT | Probability of fog (%) | 5.0 |
| `chanceofsnow` | FLOAT | Probability of snow (%) | 0.0 |
| `chanceofthunder` | FLOAT | Probability of thunderstorms (%) | 2.0 |

### Table 7: `routes_weather` (425,713 rows)

Daily weather summary along each route (already pre-aggregated from city-hour level).

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `route_id` | VARCHAR(20) | Foreign key to `routes_table` | "R_0789" |
| `Date` | DATE | Date of measurement (note: capitalized 'D' in column name) | 2019-01-15 |
| `temp` | FLOAT | Daily avg temperature (°F) | 70.1 |
| `wind_speed` | FLOAT | Daily avg wind speed (mph) | 9.0 |
| `description` | VARCHAR(50) | Dominant weather description | "Partly Cloudy" |
| `precip` | FLOAT | Daily total precipitation (inches) | 0.05 |
| `humidity` | FLOAT | Daily avg humidity (%) | 68.0 |
| `visibility` | FLOAT | Daily avg visibility (miles) | 9.5 |
| `pressure` | FLOAT | Daily avg pressure (millibars) | 1012.8 |
| `chanceofrain` | FLOAT | Daily max probability of rain | 25.0 |
| `chanceoffog` | FLOAT | Daily max probability of fog | 10.0 |
| `chanceofsnow` | FLOAT | Daily max probability of snow | 0.0 |
| `chanceofthunder` | FLOAT | Daily max probability of thunder | 5.0 |

---

## Entity Relationship Diagram (ERD)

```
┌────────────────────────────┐
│   truck_schedule_table     │       ← THE FACT TABLE
│   (12,308 rows)            │
│                            │
│ • truck_id (FK)            │────┐
│ • route_id (FK)            │──┐ │
│ • departure_date           │  │ │
│ • estimated_arrival        │  │ │
│ • delay  ★ TARGET ★        │  │ │
└────────────────────────────┘  │ │
                                │ │
                ┌───────────────┘ │
                │                 │
                ▼                 ▼
   ┌──────────────────────┐   ┌────────────────────────────┐
   │   routes_table       │   │   trucks_table             │
   │   (2,353 rows)       │   │   (1,301 rows)             │
   │                      │   │                            │
   │ • route_id (PK)      │   │ • truck_id (PK)            │
   │ • origin_id (FK)     │─┐ │ • truck_age                │
   │ • destination_id (FK)│─┤ │ • load_capacity_pounds     │
   │ • distance           │ │ │ • mileage_mpg              │
   │ • average_hours      │ │ │ • fuel_type                │
   └──────────────────────┘ │ └────────────────────────────┘
                            │              ▲
                            │              │ vehicle_no
                            │              │ (1:1 mapping)
                            │   ┌──────────────────────────┐
                            │   │   drivers_table          │
                            │   │   (1,301 rows)           │
                            │   │                          │
                            │   │ • driver_id (PK)         │
                            │   │ • name, gender, age      │
                            │   │ • experience             │
                            │   │ • driving_style          │
                            │   │ • ratings                │
                            │   │ • vehicle_no (FK)        │
                            │   │ • average_speed_mph      │
                            │   └──────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────┐
   │   city_weather             │   (referenced twice —
   │   (55,177 rows)            │    once for origin city,
   │                            │    once for destination city)
   │ • city_id (FK from         │
   │   routes.origin_id or      │
   │   routes.destination_id)   │
   │ • date, hour               │
   │ • temp, wind_speed, etc.   │
   └────────────────────────────┘


   Linked separately by route_id + date:

   ┌────────────────────────────┐    ┌────────────────────────────┐
   │   traffic_table            │    │   routes_weather           │
   │   (2,597,914 rows)         │    │   (425,713 rows)           │
   │                            │    │                            │
   │ • route_id (FK)            │    │ • route_id (FK)            │
   │ • date, hour               │    │ • Date                     │
   │ • no_of_vehicles           │    │ • temp, wind_speed, etc.   │
   │ • accident                 │    │   (already daily-aggregated)│
   └────────────────────────────┘    └────────────────────────────┘
```

### Relationships at a Glance

| From → To | Cardinality | Join Key | Notes |
|-----------|-------------|----------|-------|
| `truck_schedule_table` → `trucks_table` | many-to-one | `truck_id` | Trip → its truck |
| `truck_schedule_table` → `routes_table` | many-to-one | `route_id` | Trip → its route |
| `trucks_table` ↔ `drivers_table` | one-to-one | `truck_id = vehicle_no` | Each truck has one driver assigned |
| `routes_table` → `city_weather` (origin) | many-to-many on day | `routes.origin_id = city_weather.city_id` (+ date filter) | Origin city's weather on departure date |
| `routes_table` → `city_weather` (destination) | many-to-many on day | `routes.destination_id = city_weather.city_id` (+ date filter) | Destination city's weather on departure date |
| `routes_table` → `routes_weather` | one-to-many | `route_id` (+ date filter) | Daily weather along the route |
| `routes_table` → `traffic_table` | one-to-many | `route_id` (+ date filter) | Hourly traffic on the route |

---

## Feature Engineering — What You'll Build (Lab C)

Starting from `truck_schedule_table` (12,308 rows × 5 columns), you'll engineer the data into a **feature matrix of approximately 12,308 rows × 37 columns** (36 features + 1 target).

### Joining Strategy

The right order is **schedule → trucks → drivers → routes → aggregated traffic → aggregated weather**. The two aggregations are critical — joining `traffic_table` (2.6M rows) directly to `truck_schedule_table` would produce a Cartesian explosion.

| Step | Action | Row Count After |
|------|--------|----------------:|
| 1 | Start with `truck_schedule_table` | 12,308 |
| 2 | LEFT JOIN `trucks_table` on `truck_id` | 12,308 |
| 3 | LEFT JOIN `drivers_table` on `truck_id = vehicle_no` | 12,308 |
| 4 | LEFT JOIN `routes_table` on `route_id` | 12,308 |
| 5 | Aggregate `traffic_table` by `route_id + date` → mean(no_of_vehicles), max(accident); LEFT JOIN | 12,308 |
| 6 | Aggregate `routes_weather` by `route_id + date` → mean of all weather fields; LEFT JOIN | 12,308 |
| 7 | LEFT JOIN `city_weather` aggregated by `city_id + date` → origin weather (6 features) | 12,308 |
| 8 | LEFT JOIN `city_weather` aggregated again → destination weather (6 features) | 12,308 |
| 9 | Engineer temporal features: `hour_of_day`, `day_of_week`, `is_midnight` | 12,308 |
| 10 | Final feature matrix | **12,308 × 37** |

### Final Feature Inventory (36 features + 1 target)

**27 continuous features**
- Route weather (6): avg `temp`, `wind_speed`, `precip`, `humidity`, `visibility`, `pressure`
- Origin weather (6): same 6 from origin city
- Destination weather (6): same 6 from destination city
- Vehicle metrics (3): `truck_age`, `load_capacity_pounds`, `mileage_mpg`
- Driver metrics (3): driver `age`, `experience`, `average_speed_mph`
- Traffic (1): `avg_no_of_vehicles`
- Route metrics (2): `distance`, `average_hours`

**9 categorical features**
- Free-form: `route_description`, `origin_description`, `destination_description` (used as labels)
- Encoded: `fuel_type`, `gender`, `driving_style` (one-hot encode these)
- Already binary/ordinal: `accident` (0/1), `ratings` (1–5), `is_midnight` (0/1, engineered)

**1 target**: `delay` (0/1)

### Saved Artifacts (Lab C → Lab D → Lab E chain)

| Artifact | Created In | Used By |
|----------|-----------|---------|
| `final_features.csv` | Lab C | Lab D (model training) |
| `feature_metadata.json` (column names + types) | Lab C | Documentation / Lab D |
| `encoder.pkl` (fitted OneHotEncoder) | Lab D | Lab E (inference) |
| `scaler.pkl` (fitted StandardScaler) | Lab D | Lab E (inference) |
| `model.pkl` (best trained model, typically XGBoost) | Lab D | Lab E (inference) |
| MLflow runs (3 model runs + best registered) | Lab D | Reference / MLflow UI |

---

## Tools You'll Use

| Tool | Role | Where It Runs |
|------|------|---------------|
| **AWS EC2** | Hosts MLflow server, Streamlit app, batch scoring jobs | Cloud (provisioned for you) |
| **AWS RDS PostgreSQL 15** | Stores all 7 dataset tables | Cloud (provisioned for you) |
| **AWS S3** | Datasets, model artifacts, MLflow artifact store | Cloud (provisioned for you) |
| **AWS SageMaker Notebook** | Where you run Labs C and D | Cloud (you create one with the pre-made IAM role) |
| **MLflow** | Experiment tracking + Model Registry | Self-hosted on EC2 (already running) |
| **DBeaver** | SQL client for browsing RDS | Your laptop |
| **psycopg2 / SQLAlchemy** | Python DB drivers | Inside your notebooks |
| **scikit-learn** | Logistic Regression, Random Forest, encoders, scalers, metrics | Inside your notebooks |
| **XGBoost** | Gradient boosting classifier | Inside your notebooks |
| **Streamlit** | Interactive dashboard for predictions (Lab E) | Local or on EC2 |
| **boto3** | Python SDK for AWS (S3 read/write) | Inside your scripts |

---

## How the Module Connects to Later Modules (Spine Project Roadmap)

| Module | What Happens to the Truck Delay Project |
|--------|-----------------------------------------|
| **M3 (this)** | Build the first cloud-deployed version: RDS data, MLflow tracking, Streamlit dashboard, batch scoring |
| M4 | **Containerize** the M3 Streamlit app into Docker, push to ECR |
| M5 | Deploy the Docker container to **ECS** behind an ALB, set up **GitHub Actions CI/CD** |
| M6 | Add **drift detection** (Evidently AI), data validation (Great Expectations), alerts via SNS |
| M7 | Move features into **Hopsworks Feature Store**, expand experiment tracking with **W&B** and **SHAP** explainability |
| M8 | Orchestrate the full pipeline with **SageMaker Pipelines** + Lambda + EventBridge — the capstone |

Everything you build in M3 becomes the foundation for the next 5 modules. The dataset and the target stay the same; the tools and patterns evolve.

---

## Before You Start (Prerequisites)

You should already have:
- ✅ Python 3.12.10 installed on your laptop
- ✅ `.venv` virtual environment workflow (from M1)
- ✅ Git + GitHub account (from M1)
- ✅ A working M2 Real Estate FastAPI project (your own, locally)
- ✅ AWS account (with billing alerts set)
- ✅ AWS CLI configured (`aws configure` works; `aws sts get-caller-identity` returns your account)
- ✅ DBeaver Community Edition installed
- ✅ VS Code with Python + Jupyter extensions

Your instructor will share at the start of class:
- AWS Console URL + your IAM credentials (if using a shared training account)
- EC2 public IP + SSH `.pem` key (for connecting to MLflow / running Streamlit)
- RDS endpoint + database credentials (via Secrets Manager / handout)
- S3 bucket name
- SageMaker IAM role ARN
- MLflow UI URL

---

## What to Do If You Get Stuck

| Problem | First Try |
|---------|-----------|
| Can't connect to RDS | Check you're in the right AWS region (ap-south-1). Check DBeaver SSH tunnel is on. |
| MLflow UI won't load | Verify EC2 IP. Check port 5000 is in security group. Curl from EC2: `curl localhost:5000` |
| `psycopg2` install fails | Use `psycopg2-binary` instead of `psycopg2` |
| SageMaker notebook IAM error | Confirm the notebook instance has the `<project>-sagemaker-role` attached |
| `final_features.csv` shape isn't ~(12308, 37) | Recount rows after each merge — likely a join order or aggregation issue |
| Model accuracy seems too high (>95%) | Check for target leakage — did you accidentally include `estimated_arrival - departure_date` as a feature? |

Ask your instructor or peers. **Don't suffer in silence.**

---

## Module 3 Completion Checklist

You're done with Module 3 when:

- [ ] Lab C notebook runs end-to-end, produces `final_features.csv` with ~(12308, 37) shape
- [ ] Lab D notebook trains 3 models, logs all 3 to MLflow, registers the best one
- [ ] You can open the MLflow UI in your browser and see your 3 runs
- [ ] Lab E Streamlit app runs and shows predictions
- [ ] Lab E batch scoring script runs and writes predictions to RDS
- [ ] You can articulate the difference between real-time and batch scoring
- [ ] You can explain the feature engineering join strategy in your own words

---

*Next: Module 4 — you'll containerize this Streamlit app with Docker. The cloud infrastructure goes away at the end of M3; in M4 you'll learn how to package your work so it can run anywhere, anytime, on any machine.*
