# Complete Setup Guide: Neon Database & GitHub Actions

## Part 1: Neon Database Setup

### Option A: Simple Connection String (Recommended)

**You don't need `neonctl` for this project!** Just use the connection string directly.

#### Step 1: Get Your Connection String

1. Go to [Neon Console](https://console.neon.tech)
2. Sign up/login (free tier is fine)
3. Click **"Create Project"**
   - Name: `mcf-crawler` (or any name)
   - Region: Choose closest to you (Singapore region available)
   - PostgreSQL version: Latest stable (default)
4. Click **"Create Project"** and wait ~30 seconds

#### Step 2: Copy Connection String

1. Once project is created, you'll see the dashboard
2. Look for **"Connection string"** section
3. You'll see two options:
   - **Pooled connection** (recommended for serverless) - use this for GitHub Actions
   - **Direct connection** - use this for local development
4. Click **"Copy"** next to the connection string
   - It looks like: `postgresql://username:password@hostname.neon.tech/dbname?sslmode=require`
5. **IMPORTANT**: Save this password somewhere safe! Neon shows it only once.

#### Step 3: Initialize Database Schema

You have two options:

**Option 3a: Using Neon SQL Editor (Easiest)**
1. In Neon dashboard, click **"SQL Editor"** tab
2. Click **"New Query"**
3. Open `scripts/schema.sql` from this project
4. Copy all the SQL content
5. Paste into Neon SQL Editor
6. Click **"Run"** button
7. Verify tables were created (should see success message)

**Option 3b: Using psql command line**
```bash
# Install psql if needed (comes with PostgreSQL)
# On Windows: Download from postgresql.org
# On Mac: brew install postgresql
# On Linux: sudo apt-get install postgresql-client

# Run schema
psql "your-connection-string-here" < scripts/schema.sql
```

#### Step 4: Test Connection Locally

Create a `.env` file in the project root:

```bash
# Copy from .env.example
cp .env.example .env
```

Edit `.env` and add your connection string:

```env
DATABASE_URL=postgresql://username:password@hostname.neon.tech/dbname?sslmode=require
API_PORT=8000
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Test the connection:

```bash
# Test Python connection
python -c "from mcf.lib.storage.postgres_store import PostgresStore; import os; store = PostgresStore(os.getenv('DATABASE_URL')); print('✅ Connected!'); store.close()"
```

Or test with a small crawl:

```bash
# Set environment variable
export DATABASE_URL="your-connection-string-here"

# Run a test crawl (limit to 10 jobs)
uv run mcf crawl-incremental --db-url "$DATABASE_URL" --limit 10
```

---

### Option B: Using neonctl (Optional - Only if you want Neon CLI features)

`neonctl` is Neon's CLI tool. You only need it if you want:
- Database branching
- Automated migrations
- Neon-specific features

**If you just want to connect and use the database, skip this and use Option A above.**

#### Installing neonctl

```bash
# Requires Node.js (install from nodejs.org if needed)
npx neonctl@latest init
```

This will:
1. Ask you to login to Neon (opens browser)
2. Create a `.neon` folder with config
3. Link your project to Neon

#### Using neonctl

After `neonctl init`, you can:

```bash
# Get connection string
neonctl connection-string

# Run migrations
neonctl migrations apply

# Create database branches (for testing)
neonctl branches create test-branch
```

**However**, for this Python project, you can just use the connection string directly from the Neon dashboard (Option A), which is simpler and doesn't require Node.js.

---

## Part 2: GitHub Actions Setup

### Step 1: Push Code to GitHub

Make sure your code is pushed to GitHub:

```bash
git add .
git commit -m "Setup Neon database"
git push origin main
```

### Step 2: Add GitHub Secret

1. Go to your GitHub repository
2. Click **"Settings"** tab (top menu)
3. In left sidebar, click **"Secrets and variables"** → **"Actions"**
4. Click **"New repository secret"** button
5. Fill in:
   - **Name**: `DATABASE_URL` (exact match, case-sensitive!)
   - **Value**: Paste your Neon connection string (use the **pooled connection** string)
6. Click **"Add secret"**
7. Verify it appears in the list (value will be masked with `***`)

### Step 3: Verify Workflow File

Check that `.github/workflows/daily-crawl.yml` exists and looks correct:

```yaml
name: Daily Crawl

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch: # Allows manual trigger

jobs:
  crawl:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
      
      - name: Install dependencies
        run: uv sync
      
      - name: Run incremental crawl
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: uv run mcf crawl-incremental --db-url "$DATABASE_URL"
```

### Step 4: Test Workflow Manually

1. Go to **"Actions"** tab in GitHub
2. Click **"Daily Crawl"** workflow on the left
3. Click **"Run workflow"** dropdown button (top right)
4. Select branch: `main` (or your default branch)
5. Click **"Run workflow"** button
6. Watch it execute:
   - Green checkmark ✅ = Success
   - Red X ❌ = Failure (click to see logs)
   - Yellow circle ⏳ = Running

### Step 5: Verify It Works

After workflow completes successfully:

1. Check Neon dashboard → SQL Editor
2. Run query:
   ```sql
   SELECT COUNT(*) FROM jobs WHERE is_active = TRUE;
   ```
3. Should see job count > 0
4. Check crawl runs:
   ```sql
   SELECT * FROM crawl_runs ORDER BY finished_at DESC LIMIT 5;
   ```

---

## Part 3: Querying the Database

There are several ways to query your database and verify data:

### Option A: Using Neon SQL Editor (Easiest)

1. **Open Neon SQL Editor**
   - Go to Neon Console
   - Click **"SQL Editor"** tab
   - Click **"New Query"**

2. **Run Verification Queries**

   **Check if tables exist:**
   ```sql
   SELECT table_name 
   FROM information_schema.tables 
   WHERE table_schema = 'public' 
   ORDER BY table_name;
   ```
   Should show: `crawl_runs`, `jobs`, `job_run_status`

   **Check job count:**
   ```sql
   SELECT COUNT(*) as total_jobs FROM jobs;
   SELECT COUNT(*) as active_jobs FROM jobs WHERE is_active = TRUE;
   ```

   **Check recent crawl runs:**
   ```sql
   SELECT run_id, started_at, finished_at, total_seen, added, maintained, removed
   FROM crawl_runs
   ORDER BY finished_at DESC
   LIMIT 5;
   ```

   **View sample jobs:**
   ```sql
   SELECT job_uuid, title, company_name, location
   FROM jobs
   WHERE is_active = TRUE
   ORDER BY last_seen_at DESC
   LIMIT 10;
   ```

   **Check job details:**
   ```sql
   SELECT 
     job_uuid,
     title,
     company_name,
     location,
     LENGTH(description) as description_length,
     is_active,
     first_seen_at,
     last_seen_at
   FROM jobs
   WHERE is_active = TRUE
   ORDER BY last_seen_at DESC
   LIMIT 5;
   ```

### Option B: Using Python Query Script

A helper script is provided at `scripts/query_db.py`:

```bash
# Show database statistics
python scripts/query_db.py --db-url "$DATABASE_URL" --stats

# List recent crawl runs
python scripts/query_db.py --db-url "$DATABASE_URL" --runs --limit 10

# List jobs
python scripts/query_db.py --db-url "$DATABASE_URL" --list --limit 20

# Search jobs by keywords
python scripts/query_db.py --db-url "$DATABASE_URL" --search "software engineer"

# Get specific job details
python scripts/query_db.py --db-url "$DATABASE_URL" --job "job-uuid-here"

# Or use environment variable
export DATABASE_URL="your-connection-string"
python scripts/query_db.py --stats
```

The script uses the same `PostgresStore` class as the application, ensuring consistency.

### Option C: Using psql Command Line

If you have PostgreSQL client installed:

```bash
# Connect to database
psql "your-connection-string"

# Run queries
SELECT COUNT(*) FROM jobs WHERE is_active = TRUE;
SELECT * FROM crawl_runs ORDER BY finished_at DESC LIMIT 5;
\q  # Exit
```

### Option D: Using API Endpoints

Once API server is running:

```bash
# Start API server
uvicorn mcf.api.server:app --reload

# Query via API (in another terminal)
curl http://localhost:8000/api/crawl/stats
curl http://localhost:8000/api/jobs?limit=10
curl http://localhost:8000/api/jobs/{job_uuid}
```

Or use the frontend dashboard at http://localhost:3000

---

## Troubleshooting

### Neon Issues

**"Connection timeout"**
- Use **pooled connection** string (not direct)
- Check firewall settings
- Ensure connection string includes `?sslmode=require`

**"Schema not found"**
- Run `scripts/schema.sql` manually in Neon SQL Editor
- Verify tables exist: `SELECT * FROM information_schema.tables WHERE table_schema = 'public';`

**"Password issues"**
- Reset password in Neon dashboard → Settings → Reset password
- Update connection string everywhere (`.env` and GitHub secret)

### GitHub Actions Issues

**"Secret DATABASE_URL not found"**
- Verify exact name: `DATABASE_URL` (case-sensitive, no spaces)
- Check you're in the right repository
- Ensure secret is added under "Actions" secrets (not environment secrets)

**"Workflow not running"**
- Check file exists: `.github/workflows/daily-crawl.yml`
- Verify YAML syntax is valid
- Check workflow file is committed and pushed

**"Python version error"**
- Workflow uses Python 3.13
- If issues, change to `python-version: '3.12'` in workflow file

**"Workflow timeout"**
- Free tier allows 6 hours max
- Crawl should take 5-10 minutes
- If longer, check for errors in logs

**"Permission denied"**
- Ensure workflow has access to secrets
- Check repository settings → Actions → General → Workflow permissions

---

## Verification Checklist

After setup, verify everything:

- [ ] Neon project created
- [ ] Connection string copied and saved
- [ ] Schema tables created (check in Neon SQL Editor)
- [ ] `.env` file created with `DATABASE_URL`
- [ ] Local connection test passes
- [ ] GitHub secret `DATABASE_URL` added
- [ ] Workflow file exists and is valid
- [ ] Manual workflow run succeeds
- [ ] Data appears in Neon database after crawl
- [ ] API server connects successfully

---

## Quick Reference

### Connection String Format
```
postgresql://username:password@hostname.neon.tech/dbname?sslmode=require
```

### Environment Variables
```bash
# Local development (.env file)
DATABASE_URL=postgresql://...
API_PORT=8000
NEXT_PUBLIC_API_URL=http://localhost:8000

# GitHub Actions (set as secret)
DATABASE_URL=postgresql://... (pooled connection)
```

### Useful Commands

```bash
# Test connection
python -c "from mcf.lib.storage.postgres_store import PostgresStore; import os; store = PostgresStore(os.getenv('DATABASE_URL')); print('Connected!'); store.close()"

# Run crawl locally
uv run mcf crawl-incremental --db-url "$DATABASE_URL"

# Run API server
uvicorn mcf.api.server:app --reload --port 8000

# Check database
psql "your-connection-string" -c "SELECT COUNT(*) FROM jobs;"

# Query database using helper script
python scripts/query_db.py --db-url "$DATABASE_URL" --stats
```

---

## Cost

- **Neon Free Tier**: 3GB storage, sufficient for job listings
- **GitHub Actions Free Tier**: 2000 minutes/month
- **Daily crawl**: ~5-10 minutes = ~300 minutes/month
- **Total Cost**: $0/month ✅

---

## Need Help?

- Neon Docs: https://neon.tech/docs
- GitHub Actions Docs: https://docs.github.com/en/actions
- Check workflow logs in GitHub Actions tab for errors
