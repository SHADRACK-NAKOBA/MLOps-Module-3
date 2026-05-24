# Module 3 — Labs D and E Guide

**What, how, where, and the operations flow for the two end-of-Module-3 labs.**

| Lab | One-line summary | Format | Where to run |
|---|---|---|---|
| **D — MLOps: HP Tuning + Best-Model Selection** | PyCaret AutoML sweep + tuning; registers a new model version only when it beats the Lab C baseline | Jupyter notebook | SageMaker (PyCaret install is heavy) |
| **E — Deployment using Streamlit** | Live dashboard + cron-friendly batch scorer; auto-picks the best available model | Python project (Streamlit app + script) | EC2 (port 8501 already open in the SG) |

This document covers both labs in one place. For the broader Module 3 walkthrough see [`../M3_Student_Manual.md`](../M3_Student_Manual.md).

---

## 1. Where Labs D and E fit in the spine

```
Lab A  Tier-2 demo: what the CloudFormation stack creates
Lab B  EDA + Feature Engineering    →  final_features.csv (S3)
Lab C  Model Training + MLflow       →  XGBoost baseline (F1 ≈ 0.679), registered v1
Lab D  HP Tuning + AutoML            →  ~70 MLflow runs, registers v2 IF it beats baseline   ← you are here
Lab E  Deployment using Streamlit    →  loads "best available" model, serves predictions
```

Labs B and C produce artifacts that the *next* lab consumes. Lab D is **optional in the sense of "the baseline still works"**: if Lab D doesn't beat Lab C, you ship Lab C's XGBoost. Lab E doesn't care which one won — it auto-picks.

---

## 2. Lab D — MLOps: HP Tuning + Best-Model Selection

### What it does (step by step)

1. **Load** `final_features.csv` from S3 (same path Lab B writes to).
2. **Recreate Lab C's exact 70/15/15 stratified split** with `random_state=42`. Apples-to-apples comparison.
3. **PyCaret `setup()`** with `experiment_name="truck-delay-hp-tuning"` — a **new** MLflow experiment, separate from Lab C's `truck-delay-classification`.
4. **`compare_models(n_select=5, sort='F1')`** — sweep ~15 classifiers via 5-fold CV.
5. **`tune_model(n_iter=50)`** on the top performer — randomized search over PyCaret's HP grid.
6. **`blend_models()` + `stack_models()`** on the top 3 — ensemble experiments.
7. **Validation-set showdown**: score the 4 candidates (untuned / tuned / blend / stack) on the val split. Pick the highest F1.
8. **Test-set evaluation** — score the validation winner on Lab C's held-out test **once**. Whatever F1 we get is the honest production estimate.
9. **If `F1 > 0.679`**: refit on full data → register a new version of `truck-delay-classifier` → transition to Staging → upload the .pkl + metadata JSON to S3.
10. **If `F1 ≤ 0.679`**: report honestly. Lab C v1 stays in production. The ~70 MLflow runs are still there for the team to inspect.

### Where to run it

**SageMaker Notebook Instance** (`ml.t3.medium` is enough).

- First-run PyCaret install: 3–5 min.
- Full notebook run: ~15–25 min the first time, ~12–20 min subsequently.

Local Jupyter also works if your laptop has enough memory; Colab works too but the S3 + MLflow connections need extra setup.

### How to run

1. Clone the repo (or `git pull`) on your SageMaker notebook instance.
2. Open [`labs/M3_Lab_D_MLOps_HP_Tuning.ipynb`](M3_Lab_D_MLOps_HP_Tuning.ipynb).
3. In **Cell 1**, uncomment the `!pip install ...` line on the first run.
4. In **Cell 5** (MLflow configuration), set:
   - `MLFLOW_TRACKING_URI = "http://<your-EC2-IP>:5000"`
   - `S3_BUCKET = "mlops-m3-batch-2026-<your-aws-account-id>"`
5. Leave the experiment name (`truck-delay-hp-tuning`) and registry target (`truck-delay-classifier`) as they are.
6. Run All.

### What the operations flow looks like

```
You run notebook
   │
   ▼
[1] PyCaret setup() + compare_models()            →  ~15 MLflow runs
[2] tune_model(n_iter=50)                         →  ~50 MLflow runs
[3] blend_models, stack_models                    →  2 MLflow runs
[4] Score 4 candidates on validation set
[5] Score winner on test set (ONCE)
       │
       ├── F1 > 0.679?  YES                       →  Refit on full data
       │                                          →  Save .pkl + metadata to S3
       │                                          →  Register as v2 in MLflow Registry
       │                                          →  Transition to Staging
       │
       └── F1 ≤ 0.679?  NO                        →  Print "keep Lab C v1" message
                                                  →  Do nothing else
```

### Artifacts produced (winning path)

| Where | What |
|---|---|
| `s3://<bucket>/models/truck-delay-tuned/tuned_pipeline.pkl` | The PyCaret pipeline (bundles preprocessing + estimator) |
| `s3://<bucket>/models/truck-delay-tuned/tuned_metadata.json` | `{winner_model, test_f1, delta_vs_baseline, baseline_f1, ...}` |
| MLflow experiment `truck-delay-hp-tuning` | ~70 runs (every algorithm + tuning iteration + ensembles + final winner) |
| MLflow registry `truck-delay-classifier` v2 | Staging stage; v1 (Lab C) is preserved for rollback |

### The discipline rule

After Step 5 (test-set evaluation), **no decisions are made based on the test number**. If the tuned model disappoints, we don't re-tune, swap algorithms, or pick a different ensemble — that would contaminate the test set. We report the result honestly and either ship the winner or keep Lab C v1.

---

## 3. Lab E — Deployment using Streamlit

### What it does

Two complementary deliverables, both backed by the same `utils.py`:

| File | Role |
|---|---|
| [`M3_Lab_E_Streamlit_Deployment/app.py`](M3_Lab_E_Streamlit_Deployment/app.py) | Interactive **Streamlit dashboard**. 3 tabs (By Date / By Truck / By Route). Queries RDS for trip data, scores with the loaded model, shows risk-coded results + plots. |
| [`M3_Lab_E_Streamlit_Deployment/batch_score.py`](M3_Lab_E_Streamlit_Deployment/batch_score.py) | Cron-friendly **batch scorer**. Pulls unscored trips from `truck_schedule_with_features`, scores them, writes to a `predictions` table in RDS. |

### Three-tier model selection

`utils.load_artifacts()` returns the *best available* artifact bundle, in priority order:

```
1.  Lab D tuned PyCaret pipeline    s3://<bucket>/models/truck-delay-tuned/tuned_pipeline.pkl
        AND tuned_metadata.json shows delta_vs_baseline > 0

2.  Lab C XGBoost + encoder + scaler    s3://<bucket>/models/{xgb-truck-model,encoder,scaler}.pkl

3.  Heuristic predictor (hand-crafted scoring rule on real RDS features)
```

The metadata-JSON check in tier 1 is what guarantees we **never silently downgrade**: if Lab D ran but didn't beat the baseline, the JSON's `delta_vs_baseline` is ≤ 0 and Lab E skips it.

The sidebar tells you which tier was loaded — "Lab D tuned model", "Lab C XGBoost baseline", or "Heuristic (no .pkl)".

### Where to run it

**On the EC2 itself** is the recommended path:

- EC2's security group already exposes port 8501 to the world.
- EC2 sits inside the VPC, so it can reach the private RDS directly — no SSH tunnel needed.
- `_launch_on_ec2.sh` already reads RDS creds from `/opt/m3/config.json` that the CloudFormation UserData placed there.

Students get `http://<EC2_PUBLIC_IP>:8501` and that's it.

**Running on the laptop** works too via `run_live.sh`, but the RDS is `PubliclyAccessible=False` so you need an SSH tunnel:

```bash
ssh -i mlops-m3-batch-2026-key.pem -L 5432:<RDS_HOST>:5432 ubuntu@<EC2_DNS>
# Then in another terminal:
DB_HOST=localhost ./run_live.sh
```

### How to run on the EC2

```bash
# 0. From your laptop, copy the Lab E folder up to the EC2
EC2_DNS=$(aws cloudformation describe-stacks --stack-name m3-stack \
    --query "Stacks[0].Outputs[?OutputKey=='Ec2PublicDns'].OutputValue" \
    --output text --region ap-south-1)
PEM=mlops-m3-batch-2026-key.pem

scp -i $PEM -r labs/M3_Lab_E_Streamlit_Deployment ubuntu@$EC2_DNS:~/

# 1. SSH in
ssh -i $PEM ubuntu@$EC2_DNS

# 2. One-time: set up the streamlit venv
python3 -m venv ~/streamlit-venv
~/streamlit-venv/bin/pip install -r ~/M3_Lab_E_Streamlit_Deployment/requirements.txt

# 3. Launch
cd ~/M3_Lab_E_Streamlit_Deployment
bash _launch_on_ec2.sh

# 4. Open http://<EC2_PUBLIC_IP>:8501 in your browser
```

The `_launch_on_ec2.sh` script:

1. Reads DB creds from `/opt/m3/config.json` (placed there by the CloudFormation UserData at deploy time).
2. Exports the env vars `config.py` expects.
3. Kills any old streamlit process, launches the new one detached on `0.0.0.0:8501`.
4. Waits 20 s for the `/_stcore/health` endpoint to respond, then exits.

### How to run on the laptop (with SSH tunnel)

```bash
# In one terminal — keep this running:
ssh -i mlops-m3-batch-2026-key.pem -L 5432:<RDS_HOST>:5432 ubuntu@<EC2_DNS>

# In another terminal:
cd labs/M3_Lab_E_Streamlit_Deployment
DB_HOST=localhost ./run_live.sh
# Streamlit at http://localhost:8501
```

`run_live.sh` reads stack outputs (RDS endpoint, S3 bucket, MLflow URL, Secrets Manager ARN), fetches the RDS password from Secrets Manager, exports all env vars, and starts streamlit.

### Batch scoring (cron)

The dashboard handles ad-hoc queries. The **batch scorer** (`batch_score.py`) handles nightly jobs:

```bash
# On the EC2 — one-shot run
cd ~/M3_Lab_E_Streamlit_Deployment
python batch_score.py

# Schedule nightly at 2 AM
(crontab -l 2>/dev/null; \
 echo "0 2 * * * cd ~/M3_Lab_E_Streamlit_Deployment && \
       python batch_score.py >> ~/batch.log 2>&1") | crontab -
```

Each run:
1. Loads the same artifact bundle the dashboard uses (Lab D tuned → Lab C XGBoost → heuristic).
2. Pulls unscored rows from `truck_schedule_with_features` (the `predictions` table is the deduplication key).
3. Scores them, writes the results back to `predictions` with a `scored_at` timestamp.

---

## 4. The full operations flow (Lab C → Lab D → Lab E)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Lab B writes:   s3://<bucket>/data/processed/final_features.csv    │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Lab C trains XGBoost (+ LR + RF)                                    │
│  Logs to MLflow experiment 'truck-delay-classification'              │
│  Registers as truck-delay-classifier v1, transitions to Staging      │
│  Uploads model/encoder/scaler .pkl to s3://<bucket>/models/          │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Lab D runs PyCaret AutoML + HP tuning (~70 runs)                    │
│  Logs to MLflow experiment 'truck-delay-hp-tuning'                   │
│                                                                       │
│  IF the tuned model beats F1 = 0.679 on the held-out test set:       │
│    - Saves .pkl to s3://<bucket>/models/truck-delay-tuned/           │
│    - Saves metadata JSON with delta_vs_baseline                       │
│    - Registers as truck-delay-classifier v2, transitions to Staging  │
│    - v1 (Lab C) is preserved for rollback                            │
│                                                                       │
│  IF NOT: no S3 upload, no new registry version. Lab C v1 stays.      │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Lab E (app.py + batch_score.py) loads artifacts:                    │
│                                                                       │
│    1. Try Lab D path  (s3://.../truck-delay-tuned/tuned_pipeline.pkl)│
│       - reads tuned_metadata.json                                     │
│       - if delta_vs_baseline > 0, use it                              │
│    2. Else try Lab C path  (s3://.../{xgb,encoder,scaler}.pkl)       │
│    3. Else heuristic fallback                                         │
│                                                                       │
│  Sidebar shows which tier was loaded (Lab D / Lab C / heuristic).    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Common operations

### Re-register a model in Production

After Lab D promotes a tuned model to Staging, the next step is moving it to Production once you're happy with the live behaviour. From the MLflow UI:

```
Models → truck-delay-classifier → v2 → Stage → Transition to "Production"
```

Lab E reads from `Staging` by default. To switch it to read from `Production`, change the stage filter in `utils.py` (or use an env var if you want runtime control).

### Roll back to Lab C

```
Models → truck-delay-classifier → v1 → Stage → Transition to "Staging"
                                     → Archive v2
```

Lab E automatically picks up the latest version in Staging on the next dashboard refresh (cached resource, so restart streamlit).

### Verify which model Lab E loaded

Look at the **sidebar** of the running dashboard:
- "LIVE — Lab D tuned model" + delta vs baseline → Lab D path
- "LIVE — Lab C XGBoost baseline" + F1 = 0.679 → Lab C path
- "LIVE RDS, heuristic predictions" → no .pkl loadable
- "DEMO MODE" → no RDS connection either

### Re-run Lab D with a deeper search

In `M3_Lab_D_MLOps_HP_Tuning.ipynb` Cell labelled "Tune the top performer":

```python
tuned_top = tune_model(
    best_model,
    n_iter=200,                # 4× the default 50
    optimize="F1",
    search_library="optuna",   # TPE search beats random by 5-15%
    search_algorithm="tpe",
    choose_better=True,
    verbose=False,
)
```

This takes ~3× longer but typically improves F1 by 0.01–0.03 — sometimes enough to push past the baseline when the default 50-iter run was close.

### Teardown after the session

Lab D and Lab E don't create any AWS resources themselves; they consume the ones from the M3 CloudFormation stack. The teardown step from `M3_Student_Manual.md §14` handles everything:

```bash
aws cloudformation delete-stack --stack-name m3-stack --region <region>
```

---

## 6. Docker deployment (Module 4) and the Lab D constraint

Module 4 takes the Lab E app and packages it into a Docker image. The Dockerfile copies four files from the Lab E folder — `app.py`, `config.py`, `utils.py`, `requirements.txt` — and excludes `batch_score.py` (cron job, not a dashboard service).

### Docker = Lab C path only (by design)

The Docker image deliberately omits `pycaret` from `requirements.txt`. PyCaret pulls in XGBoost + LightGBM + CatBoost + ~30 other dependencies — it would add ~500 MB to the image and most of that weight is unused by the dashboard at runtime.

So inside the M4 container the **Lab D tuned-model path is unavailable**:

```
Docker container starts
       │
       ▼
utils.load_artifacts()
       │
       ├── Try Lab D path → pycaret import fails → skip with a log line
       │
       └── Try Lab C path → loads xgb-truck-model.pkl + encoder.pkl + scaler.pkl  ✅
```

The guard in `utils._try_load_tuned_bundle()` catches the `ImportError` and silently moves on — no crash, no surprise. The sidebar will show "LIVE — Lab C XGBoost baseline".

### Manual promotion of the Lab D tuned model (before M5 introduces CI/CD)

If Lab D produced a tuned winner and you want it serving predictions in your Docker container today (before M5 wires up CodePipeline), there are two paths:

**Path A — Add PyCaret to the image (one-off; ~500 MB heavier).**

```bash
# In Module 4/labs/M4_Lab4_Docker_Compose/app/requirements.txt, add:
pycaret==3.3.2

# Rebuild and push
cd Module\ 4/labs/M4_Lab4_Docker_Compose
docker compose build dashboard
# (or for Lab 3's ECR push:)
docker tag freshbasket-dashboard:latest <account>.dkr.ecr.<region>.amazonaws.com/<repo>:tuned-v1
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/<repo>:tuned-v1
```

This makes the container behave identically to bare-Python Lab E — both paths work, the metadata-JSON delta check decides.

**Path B — Run bare-Python on EC2 for the tuned model, Docker for everything else.**

The default. Cleaner separation:

| Component | Where |
|---|---|
| Streamlit dashboard (Lab C XGBoost) | Docker container on EC2 (or local) |
| Streamlit dashboard (Lab D tuned model) | Bare-Python on EC2, launched via `_launch_on_ec2.sh` |
| Batch scorer | Bare-Python cron (PyCaret or not — depends on which artifacts S3 has) |

Switch between them by stopping one and starting the other on port 8501. Not elegant, but it's honest about the trade-off until M5 gives us proper deployment automation.

### Quick promotion checklist (manual)

After running Lab D and confirming the tuned model beat baseline:

1. Verify the artifacts landed:
   ```bash
   aws s3 ls s3://<bucket>/models/truck-delay-tuned/
   # Expect: tuned_pipeline.pkl, tuned_metadata.json
   ```
2. Verify the metadata shows a positive delta:
   ```bash
   aws s3 cp s3://<bucket>/models/truck-delay-tuned/tuned_metadata.json - | jq .delta_vs_baseline
   # Expect: a number > 0
   ```
3. Restart Streamlit (bare-Python, NOT Docker):
   ```bash
   ssh -i mlops-m3-batch-2026-key.pem ubuntu@<EC2_DNS>
   pkill -f "streamlit run app.py" || true
   ~/streamlit-venv/bin/pip install pycaret==3.3.2     # one-off, ~3 min
   cd ~/M3_Lab_E_Streamlit_Deployment
   bash _launch_on_ec2.sh
   ```
4. Open `http://<EC2_PUBLIC_IP>:8501` and confirm the sidebar reads "LIVE — Lab D tuned model" with the test F1 displayed.

**Rollback** to the Lab C image (Docker, no pycaret) is just: stop bare-Python streamlit, restart the Docker container. Lab E's tier system handles the artifact selection automatically once pycaret is gone.

> **Why this matters (and why M5 fixes it):** Path B is operationally awkward — two ways to run the same app. Module 5 introduces ECS + CodePipeline + ECR tag-based deploys, at which point you build *one* tuned-aware image once, push it under a `tuned-vN` tag, and ECS rolls it out via a CI/CD flow. The manual promotion documented above is the "before" state we're improving on.

---

## 7. Quick reference

### Lab D
- **Notebook**: [`M3_Lab_D_MLOps_HP_Tuning.ipynb`](M3_Lab_D_MLOps_HP_Tuning.ipynb)
- **Runs on**: SageMaker
- **New MLflow experiment**: `truck-delay-hp-tuning`
- **Time**: 15–25 min
- **Outputs (conditional)**: `s3://<bucket>/models/truck-delay-tuned/{tuned_pipeline.pkl, tuned_metadata.json}` + registry v2

### Lab E
- **Folder**: [`M3_Lab_E_Streamlit_Deployment/`](M3_Lab_E_Streamlit_Deployment/)
- **Runs on**: EC2 (port 8501)
- **Launch**: `bash _launch_on_ec2.sh`
- **URL**: `http://<EC2_PUBLIC_IP>:8501`
- **Batch**: `python batch_score.py` (cron-friendly)
- **Auto-picks**: Lab D tuned → Lab C XGBoost → heuristic
