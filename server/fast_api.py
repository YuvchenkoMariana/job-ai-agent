from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.db.database import Session, JobVacancy, init_db
from backend.ai.enricher import enrich_job
from protocol.python.job import JobDescription, JobDescriptionList


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # create tables if they don't exist yet
    yield


app = FastAPI(title="Job AI Agent API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Plugin request schema  (what the Chrome extension sends)
# ---------------------------------------------------------------------------
class PluginJob(BaseModel):
    index: int = Field(ge=1, description="1-based position in the scraped list")
    title: str = Field(default="")
    href: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Test helper — exposed so tests can reset state between runs
# ---------------------------------------------------------------------------
def _clear_jobs_db() -> None:
    with Session() as session:
        session.query(JobVacancy).delete()
        session.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/jobs/sync",
    summary="Push scraped jobs from the plugin",
    response_description="How many jobs were upserted",
)
def sync_jobs(payload: list[PluginJob]) -> dict[str, int]:
    """
    Called by the Chrome extension after it finishes scraping.
    Upserts each job by source_url: insert if new, update title if exists.
    """
    if not payload:
        raise HTTPException(status_code=422, detail="Payload must not be empty")

    count = 0
    with Session() as session:
        for item in payload:
            job_title = item.title.strip()
            source_url = (item.href or "").strip()

            if not job_title and not source_url:
                continue

            existing = (
                session.query(JobVacancy)
                .filter_by(source_url=source_url)
                .first()
            )
            if existing:
                existing.job_title = job_title
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(JobVacancy(
                    job_title=job_title,
                    source_url=source_url,
                ))
            count += 1

        session.commit()

    return {"count": count}


@app.get(
    "/api/jobs",
    summary="Get all job descriptions from the database",
)
def get_jobs() -> list[dict]:
    """Returns all jobs stored in the database, ordered by id."""
    with Session() as session:
        rows = session.query(JobVacancy).order_by(JobVacancy.id).all()
        return JobDescriptionList(
            jobs=[JobDescription.from_row(r) for r in rows]
        ).to_list()


# ---------------------------------------------------------------------------
# AI enrichment
# ---------------------------------------------------------------------------

@app.post(
    "/api/jobs/{job_id}/enrich",
    summary="Enrich one job with AI — fetches the page and fills in null fields",
)
def enrich_one(job_id: int) -> dict:
    with Session() as session:
        job = session.query(JobVacancy).filter_by(id=job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        if not job.source_url:
            raise HTTPException(status_code=422, detail="Job has no source_url to fetch")

        enriched = enrich_job(source_url=job.source_url, job_title=job.job_title)

        for field, value in enriched.items():
            if hasattr(job, field) and value is not None:
                setattr(job, field, value)
        job.updated_at = datetime.now(timezone.utc)
        session.commit()

        return JobDescription.from_row(job).to_dict()


@app.post(
    "/api/jobs/enrich-all",
    summary="Enrich all jobs that still have empty fields",
)
def enrich_all() -> dict[str, int]:
    """Enriches every job whose role_summary is still null."""
    enriched_count = 0
    failed_count = 0

    with Session() as session:
        jobs = (
            session.query(JobVacancy)
            .filter(JobVacancy.role_summary.is_(None), JobVacancy.source_url.isnot(None))
            .all()
        )

        for job in jobs:
            try:
                data = enrich_job(source_url=job.source_url, job_title=job.job_title)
                for field, value in data.items():
                    if hasattr(job, field) and value is not None:
                        setattr(job, field, value)
                job.updated_at = datetime.now(timezone.utc)
                enriched_count += 1
            except Exception as e:
                print(f"[enrich-all] job {job.id} failed: {e}")
                failed_count += 1

        session.commit()

    return {"enriched": enriched_count, "failed": failed_count}

