# Teardown — Verified Checklist

> Run teardown in this order. CloudFormation cannot delete the stack while S3 has objects
> (versioning is enabled), so empty the bucket first.

---

## 1. Stop and Delete SageMaker Notebook Instance

If you did not do this at the end of Lab D, do it first (it incurs hourly charges even when stopped).

```bash
# Stop (must reach Stopped status before deleting)
aws sagemaker stop-notebook-instance \
  --notebook-instance-name <NOTEBOOK_NAME> --region <AWS_REGION>

# Poll until Stopped:
aws sagemaker describe-notebook-instance \
  --notebook-instance-name <NOTEBOOK_NAME> --region <AWS_REGION> \
  --query NotebookInstanceStatus

# Delete
aws sagemaker delete-notebook-instance \
  --notebook-instance-name <NOTEBOOK_NAME> --region <AWS_REGION>
```

> **Note:** A pre-existing `Zero-Shot` SageMaker notebook (already stopped, not part of
> this project) was present in the account and intentionally left alone.

---

## 2. Empty S3 Bucket (All Versions + Delete Markers)

Because versioning is enabled, `aws s3 rm --recursive` only removes current versions.
CloudFormation will refuse to delete the stack while the bucket is non-empty.

Use the boto3 pagination script below — the AWS CLI `--delete` JSON one-liner is
unreliable on Windows Git Bash due to quoting/escaping issues (see
`03-Issues-and-Fixes.md` §23).

```python
# empty_bucket.py  — run locally or on EC2
import boto3

BUCKET = '<S3_BUCKET>'
REGION = '<AWS_REGION>'

s3 = boto3.client('s3', region_name=REGION)
paginator = s3.get_paginator('list_object_versions')

for page in paginator.paginate(Bucket=BUCKET):
    objects_to_delete = []

    for v in page.get('Versions', []):
        objects_to_delete.append({'Key': v['Key'], 'VersionId': v['VersionId']})

    for dm in page.get('DeleteMarkers', []):
        objects_to_delete.append({'Key': dm['Key'], 'VersionId': dm['VersionId']})

    if objects_to_delete:
        resp = s3.delete_objects(
            Bucket=BUCKET,
            Delete={'Objects': objects_to_delete, 'Quiet': True}
        )
        errors = resp.get('Errors', [])
        if errors:
            print('Errors:', errors)
        else:
            print(f'Deleted {len(objects_to_delete)} object versions/markers')

print('Bucket empty.')
```

```bash
python3 empty_bucket.py
```

---

## 3. Delete CloudFormation Stack

```bash
aws cloudformation delete-stack \
  --stack-name m3-stack \
  --region <AWS_REGION>
```

Monitor deletion:

```bash
aws cloudformation describe-stacks \
  --stack-name m3-stack \
  --region <AWS_REGION> \
  --query "Stacks[0].StackStatus"
```

Expected final status: `DELETE_COMPLETE` (or stack disappears from list — both mean success).

If you get `DELETE_FAILED` with `bucket not empty`, the S3 step above didn't complete.
Re-run `empty_bucket.py` and retry.

---

## 4. Delete Local `.pem` File

```bash
rm <PROJECT_NAME>-key.pem
```

Verify:

```bash
ls *.pem   # should return nothing
```

---

## 5. Delete AWS-Side EC2 Key Pair

```bash
aws ec2 delete-key-pair \
  --key-name <PROJECT_NAME>-key \
  --region <AWS_REGION>
```

This removes the public key from AWS. The `.pem` (private key) is already gone from step 4.

---

## 6. Full Verification Block

Run this after stack deletion completes. Each section should return empty / not-found results.

```bash
#!/usr/bin/env bash
set -euo pipefail
REGION=<AWS_REGION>
PROJECT=<PROJECT_NAME>

echo "=== CloudFormation Stack ==="
aws cloudformation describe-stacks \
  --stack-name m3-stack --region "$REGION" 2>&1 || echo "STACK GONE (expected)"

echo ""
echo "=== EC2 Instances ==="
aws ec2 describe-instances \
  --filters "Name=tag:aws:cloudformation:stack-name,Values=m3-stack" \
  --region "$REGION" \
  --query "Reservations[*].Instances[*].{ID:InstanceId,State:State.Name}" \
  --output table

echo ""
echo "=== RDS Instances ==="
aws rds describe-db-instances \
  --region "$REGION" \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$PROJECT')].{ID:DBInstanceIdentifier,Status:DBInstanceStatus}" \
  --output table

echo ""
echo "=== S3 Bucket ==="
aws s3 ls s3://"$PROJECT"-data 2>&1 || echo "BUCKET GONE or EMPTY (expected)"

echo ""
echo "=== VPC ==="
aws ec2 describe-vpcs \
  --filters "Name=tag:aws:cloudformation:stack-name,Values=m3-stack" \
  --region "$REGION" \
  --query "Vpcs[*].VpcId" \
  --output table

echo ""
echo "=== IAM Roles ==="
aws iam list-roles \
  --query "Roles[?contains(RoleName, '$PROJECT')].RoleName" \
  --output table

echo ""
echo "=== Secrets Manager ==="
aws secretsmanager list-secrets \
  --region "$REGION" \
  --query "SecretList[?contains(Name, '$PROJECT')].Name" \
  --output table

echo ""
echo "=== EC2 Key Pair ==="
aws ec2 describe-key-pairs \
  --region "$REGION" \
  --key-names "$PROJECT-key" 2>&1 || echo "KEY PAIR GONE (expected)"

echo ""
echo "=== CloudWatch Alarms ==="
aws cloudwatch describe-alarms \
  --region "$REGION" \
  --query "MetricAlarms[?contains(AlarmName, '$PROJECT')].AlarmName" \
  --output table

echo ""
echo "=== SNS Topics ==="
aws sns list-topics \
  --region "$REGION" \
  --query "Topics[*].TopicArn" \
  --output table

echo ""
echo "=== SageMaker Notebook Instances ==="
aws sagemaker list-notebook-instances \
  --region "$REGION" \
  --query "NotebookInstances[?contains(NotebookInstanceName, '$PROJECT')].{Name:NotebookInstanceName,Status:NotebookInstanceStatus}" \
  --output table
```

---

## Final Verified Status

| Resource | Status |
|----------|--------|
| CloudFormation stack `m3-stack` | DELETED |
| EC2 instance | TERMINATED (via stack deletion) |
| RDS instance | DELETED (via stack deletion) |
| S3 bucket | DELETED (after emptying all versions) |
| VPC + subnets + IGW + SGs | DELETED (via stack deletion) |
| IAM roles / instance profiles | DELETED (via stack deletion) |
| Secrets Manager secret | DELETED (via stack deletion) |
| EC2 key pair (AWS-side) | DELETED manually |
| Local `.pem` file | DELETED manually |
| SageMaker notebook (`<PROJECT_NAME>-hp-tuning`) | DELETED |
| CloudWatch alarms | DELETED (via stack deletion) |
| SNS topics | DELETED (via stack deletion) |
| `Zero-Shot` SageMaker notebook | **UNTOUCHED** — pre-existing, not part of this project |
