# Production Migration Overview

## What M3 Is (Learning / Demo)

The M3 deployment is a deliberately simple, self-contained stack designed for hands-on
learning. It runs the entire ML platform on a **single EC2 instance**, with publicly
accessible endpoints and permissive network rules. It is intentionally not production-grade.

| Characteristic | M3 (Learning) |
|---------------|---------------|
| MLflow server | Single EC2, public IP, port 5000 open to `0.0.0.0/0` |
| Streamlit dashboard | Same EC2, port 8501 open to `0.0.0.0/0` |
| Network | Default VPC, public subnets |
| Security groups | `0.0.0.0/0` ingress on application ports |
| TLS/HTTPS | None |
| Autoscaling | None |
| RDS | Single-AZ, no automated backups beyond RDS defaults |
| Secrets | Retrieved ad-hoc from Secrets Manager; not injected via IAM |
| Batch scorer | Cron on EC2; single point of failure |
| Model promotion | Manual (notebook-driven) |
| Cost controls | Single `<$10` billing alarm |

## What Production Needs

| Concern | Production Pattern |
|---------|-------------------|
| MLflow | ECS/Fargate service behind an ALB, or a managed service (Databricks MLflow, SageMaker Model Registry) |
| Dashboard | Containerized (Module 4 → Module 5 pattern); ECS + ALB + HTTPS |
| Network | Private subnets for RDS and compute; ALB in public subnet only |
| Security groups | Least-privilege CIDRs / SG-to-SG references, no `0.0.0.0/0` |
| TLS | ACM certificate + HTTPS listener on ALB (Module 5) |
| Autoscaling | ECS service autoscaling based on CPU/request count |
| RDS | Multi-AZ, automated backups, parameter group review, no public access |
| Secrets | Secrets Manager with automatic rotation Lambda; secrets injected at task start via ECS task role |
| Batch scorer | EventBridge rule → Lambda or ECS task (Module 6/8 Airflow pattern) |
| Model promotion | Gated step in CI/CD pipeline: Staging → Production only after evaluation threshold is met |
| IaC | Reviewed and version-controlled CloudFormation / Terraform / CDK |
| Observability | CloudWatch dashboards, structured logging, latency/error alarms with on-call runbooks |
| Cost controls | Per-environment budget alarms; scale-to-zero options documented |

## Relationship to Other Modules

| Module | Adds |
|--------|------|
| **M3 (this repo)** | First cloud ML deployment: EC2 + RDS + S3 + MLflow + Streamlit |
| **M4** | Containerizes the Streamlit app (Docker, ECR) |
| **M5** | Deploys container to ECS + ALB + HTTPS |
| **M6** | Replaces manual batch cron with Airflow DAG / Step Functions |
| **M8** | CI/CD pipeline for model retraining and gated promotion |

## Files in This Folder

| File | Contents |
|------|---------|
| `01-Pre-Production-Checklist.md` | What must be done before promoting to production |
| `02-Migration-Steps.md` | Step-by-step migration from learning account to production |
| `03-Go-Live-Checklist.md` | Final gate before traffic cutover |
| `04-FAQ.md` | Common questions from engineers encountering this stack |
