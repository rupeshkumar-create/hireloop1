# Hireloop — Infrastructure Bootstrap Guide

Run these steps **once** before `terraform apply` works. Do them in order.

---

## Prerequisites

Install locally:
```bash
brew install awscli terraform pnpm supabase/tap/supabase
pip install uv
nvm install 20.17.0 && nvm use 20.17.0
npm install -g pnpm@9.12.2
```

---

## Step 1 — GitHub

1. Create org (or use personal): `github.com/<your-org>/hireloop-app`
2. Push this repo:
   ```bash
   cd /Users/rupesh/Claude/hireloop-app
   git init
   git add .
   git commit -m "feat: P01+P02 — repo scaffold + infra skeleton"
   git remote add origin git@github.com:<your-org>/hireloop-app.git
   git push -u origin main
   ```
3. Create branch protection on `main`: require PR + 1 review + CI passing

---

## Step 2 — Supabase project

1. Go to https://supabase.com → New project
   - **Name**: `hireloop-staging`
   - **Region**: `ap-south-2` (Hyderabad, IN) ← pick closest India region
   - **Password**: generate strong password, save to 1Password
2. Note your **Project URL** and **anon key** (Settings → API)
3. Note your **service_role key** (Settings → API → service_role — keep secret!)
4. Enable extensions (Settings → Database → Extensions):
   - `vector` (pgvector)
   - `pg_cron`
   - `pg_net`
   - `uuid-ossp`

---

## Step 3 — AWS account setup

1. Create AWS account (or use existing) — **enable ap-south-1 region**
2. Create IAM user for Terraform:
   - Name: `hireloop-terraform`
   - Attach policy: `AdministratorAccess` (tighten post-MVP)
   - Save access key + secret key
3. Configure AWS CLI:
   ```bash
   aws configure --profile hireloop
   # Enter access key, secret key, region: ap-south-1, output: json
   export AWS_PROFILE=hireloop
   ```
4. Bootstrap Terraform state backend:
   ```bash
   # Create S3 bucket for state
   aws s3api create-bucket \
     --bucket hireloop-terraform-state \
     --region ap-south-1 \
     --create-bucket-configuration LocationConstraint=ap-south-1

   aws s3api put-bucket-versioning \
     --bucket hireloop-terraform-state \
     --versioning-configuration Status=Enabled

   aws s3api put-bucket-encryption \
     --bucket hireloop-terraform-state \
     --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

   # Create DynamoDB table for state locks
   aws dynamodb create-table \
     --table-name hireloop-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST \
     --region ap-south-1
   ```
5. Uncomment the `backend "s3"` block in `infra/terraform/main.tf`

---

## Step 4 — Cloudflare setup

1. Add `hireloop.in` domain to Cloudflare (free plan is fine for start)
2. Update nameservers at your domain registrar to Cloudflare's NS
3. Create API token:
   - Go to https://dash.cloudflare.com → Profile → API Tokens
   - Create token with permissions:
     - Zone: `hireloop.in` → Zone Settings: Edit
     - Zone: `hireloop.in` → DNS: Edit
     - Zone: `hireloop.in` → Firewall Services: Edit
   - Save token
4. Note Zone ID (Overview page, right sidebar)

---

## Step 5 — Terraform apply (staging)

```bash
cd infra/terraform/envs/staging
cp terraform.tfvars.example terraform.tfvars
# Fill in real values in terraform.tfvars

cd ../..   # back to infra/terraform/
terraform init
terraform workspace new staging
terraform plan -var-file=envs/staging/terraform.tfvars
terraform apply -var-file=envs/staging/terraform.tfvars
```

---

## Step 6 — Vercel setup

1. Go to https://vercel.com → Import Project → select `hireloop-app` repo
2. Configure **two projects**:

   **Project 1 — web (marketing site)**
   - Root Directory: `web`
   - Framework: Next.js
   - Environment Variables (copy from `web/.env.example`)
   - Custom Domain: `hireloop.in` + `www.hireloop.in`

   **Project 2 — app (SPA)**
   - Root Directory: `app`
   - Framework: Next.js
   - Environment Variables (copy from `app/.env.example`)
   - Custom Domain: `app.hireloop.in`

3. Both projects will get Cloudflare CNAME records from Terraform (Step 5)

---

## Step 7 — GitHub Actions secrets

Add these secrets in GitHub repo Settings → Secrets and variables → Actions:

| Secret name | Value source |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user access key (staging deployer) |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key (staging deployer) |
| `AWS_ACCESS_KEY_ID_PROD` | IAM user access key (prod deployer) |
| `AWS_SECRET_ACCESS_KEY_PROD` | IAM user secret key (prod deployer) |
| `VERCEL_TOKEN` | Vercel → Settings → Tokens |
| `VERCEL_ORG_ID` | `vercel whoami --json` |

For staging Vercel project IDs, run `vercel link` in `web/` and `app/` directories.

---

## Step 8 — AWS Secrets Manager

Populate secrets so ECS tasks can read them:

```bash
# Helper function
put_secret() {
  aws secretsmanager create-secret \
    --name "hireloop/staging/$1" \
    --secret-string "$2" \
    --region ap-south-1
}

put_secret "database-url"        "postgresql+asyncpg://..."
put_secret "supabase-url"        "https://xxx.supabase.co"
put_secret "supabase-service-key" "eyJ..."
put_secret "openrouter-api-key"  "sk-or-v1-..."
put_secret "secret-key"          "$(openssl rand -hex 32)"
```

---

## Verification checklist

- [ ] `git push` triggers CI green on all 3 workflows (web/app/api)
- [ ] `https://hireloop.in` shows Coming Soon page
- [ ] `https://app.hireloop.in` shows Signup placeholder
- [ ] `https://api.hireloop.in/api/v1/health` returns `{"status":"ok",...}`
- [ ] Cloudflare WAF blocks a request from a VPN/US IP with 403
- [ ] Supabase project accessible from API health check (P03 adds DB check)
