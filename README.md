# mcf

MyCareersFuture job crawler and matcher for Singapore - local personal use.

## Features

- **Job Scraping**: Incremental crawling of MyCareersFuture job listings
- **Resume Matching**: Match your resume against scraped jobs using semantic similarity
- **Interaction Tracking**: Track which jobs you've viewed, applied to, or dismissed
- **Local Database**: DuckDB for local storage (no cloud required)
- **Web Dashboard**: Simple localhost UI for viewing matches and managing interactions

## Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 2. Place Your Resume

Create a `resume/` folder and place your resume file there:

```bash
mkdir resume
# Place your resume as: resume/resume.pdf (or .docx, .txt, .md)
```

Supported formats: `.pdf`, `.docx`, `.txt`, `.md`

### 3. Process Your Resume

```bash
# Process resume and create profile
uv run mcf process-resume
```

This will:
- Extract text from your resume
- Create a profile
- Generate an embedding for matching

### 4. Crawl Jobs

```bash
# Crawl new jobs (run this daily)
uv run mcf crawl-incremental
```

This will:
- Fetch new jobs from MyCareersFuture
- Generate embeddings for job descriptions
- Store basic info + URLs (descriptions not stored to save space)

### 5. Find Matches

**Via CLI:**
```bash
# Find matching jobs
uv run mcf match-jobs
```

**Via Web Dashboard:**
```bash
# Start API server (terminal 1)
uvicorn mcf.api.server:app --reload --port 8000

# Start frontend (terminal 2)
cd frontend
npm run dev
```

Open http://localhost:3000 and click "Find Matches"

## Usage

### CLI Commands

**Process resume:**
```bash
mcf process-resume
# Or specify custom path:
mcf process-resume --resume path/to/resume.pdf
```

**Crawl jobs:**
```bash
# Default: uses data/mcf.duckdb
mcf crawl-incremental

# Custom database path:
mcf crawl-incremental --db path/to/database.duckdb

# Limit for testing:
mcf crawl-incremental --limit 100
```

**Find job matches:**
```bash
# Find top 25 matches (excludes interacted jobs)
mcf match-jobs

# Include interacted jobs:
mcf match-jobs --include-interacted

# Get more matches:
mcf match-jobs --top-k 50
```

**Mark job interaction:**
```bash
mcf mark-interaction <job-uuid> --type viewed
mcf mark-interaction <job-uuid> --type applied
mcf mark-interaction <job-uuid> --type dismissed
mcf mark-interaction <job-uuid> --type saved
```

**Full crawl to parquet (for one-time exports):**
```bash
mcf crawl --output data/jobs
```

### API Endpoints

- `GET /api/profile` - Get profile and resume status
- `POST /api/profile/process-resume` - Process resume from file
- `GET /api/matches` - Get job matches for your resume
- `GET /api/jobs` - List jobs (excludes interacted by default)
- `GET /api/jobs/{job_uuid}` - Get job basic info
- `POST /api/jobs/{job_uuid}/interact` - Mark job as interacted
- `GET /api/health` - Health check

### Daily Workflow

1. **Morning**: Run `mcf crawl-incremental` to fetch new jobs
2. **Afternoon**: Open dashboard at http://localhost:3000
3. **Click "Find Matches"**: See new jobs matching your resume
4. **Interact with jobs**: Click "Viewed", "Applied", "Dismissed", or "Save"
5. **Next day**: Only new/unviewed jobs will appear (interacted jobs are filtered out)

## Architecture

- **Backend**: FastAPI (Python)
- **Frontend**: Next.js 14 (React, TypeScript)
- **Database**: DuckDB (local file-based, no server needed)
- **Storage**: Only stores embeddings + basic info + URLs (no full descriptions)

## Configuration

Default paths (can be overridden via environment variables):

- Database: `data/mcf.duckdb`
- Resume: `resume/resume.pdf`
- User ID: `default_user`

Set via environment variables:
```bash
export DB_PATH=data/mcf.duckdb
export RESUME_PATH=resume/resume.pdf
export DEFAULT_USER_ID=default_user
export API_PORT=8000
```

## Development Guide

### How to Add New Packages

To add a new production dependency:
```bash
uv add requests
```

To add a new development dependency:
```bash
uv add --dev ipdb
```

After adding dependencies, always re-generate requirements.txt:
```bash
uv pip compile pyproject.toml -o requirements.txt
```

## File Structure

```
mcf-main/
├── resume/              # Place your resume here (gitignored)
├── data/               # Database files (gitignored)
├── src/mcf/
│   ├── api/            # FastAPI server
│   ├── cli/            # CLI commands
│   ├── lib/
│   │   ├── crawler/    # Job crawler
│   │   ├── storage/    # DuckDB storage
│   │   ├── embeddings/ # Embedding generation
│   │   └── pipeline/   # Crawl pipeline
└── frontend/           # Next.js dashboard
```

## Notes

- Job descriptions are **not stored** in the database to save space
- Only embeddings, basic info (title, company, location), and URLs are stored
- Click job URLs to see full descriptions on MyCareersFuture
- Jobs you've interacted with won't appear in future matches (unless you include them)
- Matches are sorted by similarity score, then by recency (newest first)

## License

MIT
