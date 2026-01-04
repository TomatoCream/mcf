# mcf

MyCareersFuture job crawler for Singapore.

## Usage

### CLI

Crawl all jobs to parquet:

```bash
mcf crawl
```

Options:
- `-o, --output` — Output directory (default: `data/jobs`)
- `-r, --rate-limit` — Requests per second (default: 4.0)
- `-l, --limit` — Max jobs to fetch (for testing)

### Library

```python
from mcf.lib.api.client import MCFClient
from mcf.lib.crawler.crawler import Crawler

# Direct API access
with MCFClient() as client:
    results = client.search_jobs(keywords="python", limit=10)
    job = client.get_job_detail(results.results[0].uuid)

# Batch crawl
crawler = Crawler(rate_limit=5.0)
result = crawler.crawl(categories=["Information Technology"], limit=100)
df = result.jobs  # pandas DataFrame
```

---

## Development Guide

### How to Add New Packages

To add a new production dependency (e.g., 'requests'):
```bash
uv add requests
```

To add a new development dependency (e.g., 'ipdb'):
```bash
uv add --dev ipdb
```

After adding dependencies, always re-generate requirements.txt:
```bash
uv pip compile pyproject.toml -o requirements.txt
```

### How to Build Packages

To build your project's distributable packages (.whl, .tar.gz):
```bash
python -m build
```

Or using the virtual environment directly:
```bash
./venv/bin/python -m build
```

### Offline Build

To build offline packages for deployment:
```bash
./dev_scripts/build_offline.sh
```

This will create offline_packages/ with all dependencies and install.sh
