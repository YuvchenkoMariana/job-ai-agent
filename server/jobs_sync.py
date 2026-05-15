"""Shared job upsert logic.

We reuse the same upsert implementation in:
- FastAPI endpoint: POST /api/jobs/sync (used by the Chrome extension)
- Selenium scraper: server/scraper.py (runs locally on the server)

Keeping this in a separate module avoids circular imports between
`server.fast_api` and `server.scraper`.
"""

from __future__ import annotations

import logging

from backend.db.database import Session, JobPosting
from protocol.python.job import JobDescriptionList

logger = logging.getLogger(__name__)


def upsert_jobs(payload: JobDescriptionList) -> list[str]:
    """Upsert jobs into the *global* job catalog.

    Upsert key: source_url

    Returns:
        List of job_postings.id (UUID strings, in the same order as processed items).
    """

    if not payload.jobs:
        return []

    ids: list[str] = []
    with Session() as session:
        for item in payload.jobs:
            job_title = (item.job_title or "").strip()
            source_url = (item.source_url or "").strip()

            if not job_title and not source_url:
                continue

            if not source_url:
                # Without a stable URL we cannot de-dup globally.
                continue

            existing = session.query(JobPosting).filter_by(source_url=source_url).first()
            if existing:
                if job_title and (existing.job_title or "") != job_title:
                    existing.job_title = job_title
                ids.append(str(existing.id))
            else:
                title = job_title or source_url
                new = JobPosting(job_title=title, source_url=source_url)
                session.add(new)
                session.flush()
                ids.append(str(new.id))

        session.commit()

    logger.info("upsert_jobs upserted %d job(s)", len(ids))
    return ids

