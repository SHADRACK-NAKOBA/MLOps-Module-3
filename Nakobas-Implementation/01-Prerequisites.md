# Prerequisites

## AWS

### CLI

```bash
# Install AWS CLI v2 (https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
aws configure
# AWS Access Key ID:     <YOUR_ACCESS_KEY_ID>
# AWS Secret Access Key: <YOUR_SECRET_ACCESS_KEY>
# Default region:        <AWS_REGION>          # session used: us-east-1
# Default output format: json
```

Verify: `aws sts get-caller-identity`

### IAM Permissions

The IAM user / role running the deploy script needs the following service permissions:

| Service | Why |
|---------|-----|
| EC2 / VPC | Provision instance, security groups, subnets, IGW |
| RDS | Provision PostgreSQL cluster |
| S3 | Create bucket, put/get objects, manage versioning |
| IAM | Create EC2 instance profile, SageMaker execution role |
| Secrets Manager | Store / retrieve RDS master password |
| SSM | Used by EC2 bootstrapping |
| CloudFormation | Deploy and delete the stack |
| SageMaker | Create / start / stop notebook instance |
| CloudWatch + SNS | Billing alarm + email notification |

> **Simplest option for a personal account:** attach `AdministratorAccess` to your IAM user.
> Never do this in a shared or production account — see `../PROD-Implementation/01-Pre-Production-Checklist.md`.

---

## Local Machine

### Shell

- **Windows:** Git Bash (MINGW64). All commands in this repo's scripts use POSIX syntax.
- **Mac/Linux:** native bash/zsh.

> All Windows-specific gotchas (CRLF line endings, path mangling, `/tmp/` issues) are
> catalogued in `03-Issues-and-Fixes.md`.

### `jq`

Required by `deploy_m3.sh` to parse JSON responses from AWS CLI.

```bash
# Windows Git Bash — install to ~/bin (NOT /usr/bin — permission denied on managed installs)
mkdir -p ~/bin
curl -Lo ~/bin/jq https://github.com/jqlang/jq/releases/latest/download/jq-win64.exe
chmod +x ~/bin/jq
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
jq --version
```

### Python

Version **3.10+** required (tested with 3.10 and 3.11).

```bash
python --version   # or python3 --version
```

Install all required packages:

```bash
pip install \
  boto3 \
  psycopg2-binary \
  sqlalchemy \
  pandas \
  numpy \
  matplotlib \
  seaborn \
  scikit-learn \
  xgboost \
  mlflow \
  streamlit \
  joblib \
  pyyaml \
  python-dotenv \
  plotly \
  ipykernel \
  ipywidgets \
  jupyter
```

> On **SageMaker** (Lab D), install additionally:
> ```bash
> pip install pycaret==3.3.2 optuna mlflow boto3
> ```

### VS Code Extensions

Required to open `.ipynb` notebooks:

- **Python** (Microsoft, `ms-python.python`)
- **Jupyter** (Microsoft, `ms-toolsai.jupyter`)

Without these, VS Code renders the notebook as raw JSON. See `03-Issues-and-Fixes.md` §4.

### Git

```bash
git --version   # any modern version
```

---

## Config File

Before running `deploy_m3.sh`, set values in `AWS_setup/config.yaml`:

```yaml
project_name: <PROJECT_NAME>    # e.g. mlops-m3
aws_region:   <AWS_REGION>      # e.g. us-east-1
alert_email:  <EMAIL>           # billing alarm destination
billing_alert_threshold_usd: 10
```

> **Known issue:** the billing threshold must be stored as a bare number (not quoted).
> See `03-Issues-and-Fixes.md` §1 for the fix if you hit a CloudFormation ValidationError.
