"""Background scheduler for automated crawls."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Thread
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from mcf.api.config import settings
from mcf.lib.pipeline.incremental_crawl import run_incremental_crawl
from mcf.lib.storage.duckdb_store import DuckDBStore
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig

logger = logging.getLogger(__name__)


def run_crawl_job():
    """Run incremental crawl job."""
    try:
        logger.info("Starting scheduled incremental crawl")
        db_path = Path(settings.db_path)
        result = run_incremental_crawl(db_path=db_path, rate_limit=4.0)
        logger.info(
            f"Crawl complete: added={len(result.added)}, maintained={len(result.maintained)}, removed={len(result.removed)}"
        )

        # Auto-embed new jobs
        if result.added:
            logger.info(f"Embedding {len(result.added)} new jobs")
            store = DuckDBStore(db_path)
            try:
                embedder = Embedder(EmbedderConfig())
                missing = store.jobs_missing_embeddings(limit=1000)
                if missing:
                    texts = [desc or "" for _, desc in missing]
                    vectors = embedder.embed_texts(texts)
                    for (job_uuid, _), vec in zip(missing, vectors, strict=True):
                        store.upsert_embedding(
                            job_uuid=job_uuid, model_name=embedder.model_name, embedding=vec
                        )
                    logger.info(f"Embedded {len(missing)} jobs")
            finally:
                store.close()
    except Exception as e:
        logger.error(f"Error in crawl job: {e}", exc_info=True)


def start_scheduler():
    """Start the background scheduler."""
    scheduler = BackgroundScheduler()
    # Run daily at 2 AM
    scheduler.add_job(
        run_crawl_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_crawl",
        name="Daily incremental crawl",
    )
    scheduler.start()
    logger.info("Scheduler started - daily crawl scheduled at 2 AM")
    return scheduler
