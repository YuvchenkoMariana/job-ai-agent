from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.db.database import Session, JobVacancy, init_db
from backend.ai.enricher import fetch_and_save_text, enrich_from_text
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
def sync_jobs(payload: JobDescriptionList) -> dict[str, int]:
    """
    Called by the Chrome extension after it finishes scraping.
    Upserts each job by source_url: insert if new, update title if exists.
    """
    if not payload.jobs:
        raise HTTPException(status_code=422, detail="Payload must not be empty")

    count = 0
    with Session() as session:
        for item in payload.jobs:
            job_title = item.job_title.strip()
            source_url = (item.source_url or "").strip()

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
# AI enrichment — Step 2 + Step 3
# ---------------------------------------------------------------------------

@app.post(
    "/api/jobs/{job_id}/fetch-text",
    summary="Step 2 — fetch job page and save full text to DB",
)
def fetch_text_one(job_id: int) -> dict[str, int]:
    """Fetches source_url for job_id and stores the raw page text in full_text."""
    try:
        text = fetch_and_save_text(job_id)
        return {"job_id": job_id, "chars": len(text)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/api/jobs/fetch-text-all",
    summary="Step 2 for all jobs — fetch page text for every job without full_text",
)
def fetch_text_all() -> dict[str, int]:
    """Fetches and saves page text for all jobs where full_text is still null."""
    done, failed = 0, 0
    with Session() as session:
        jobs = session.query(JobVacancy).filter(
            JobVacancy.full_text.is_(None),
            JobVacancy.source_url.isnot(None),
        ).all()
        ids = [j.id for j in jobs]

    for job_id in ids:
        try:
            fetch_and_save_text(job_id)
            done += 1
        except Exception as e:
            print(f"[fetch-text-all] job {job_id} failed: {e}")
            failed += 1

    return {"done": done, "failed": failed}


@app.post(
    "/api/jobs/{job_id}/enrich",
    summary="Step 3 — read full_text from DB and fill fields using OpenAI",
)
def enrich_one(job_id: int) -> dict:
    """Reads full_text for job_id, calls OpenAI, saves structured fields to DB."""
    try:
        return enrich_from_text(job_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post(
    "/api/jobs/enrich-all",
    summary="Step 3 for all jobs — enrich every job that has full_text but no role_summary",
)
def enrich_all() -> dict[str, int]:
    """Enriches all jobs that have full_text but not yet a role_summary."""
    done, failed = 0, 0
    with Session() as session:
        ids = [
            j.id for j in session.query(JobVacancy).filter(
                JobVacancy.full_text.isnot(None),
                JobVacancy.role_summary.is_(None),
            ).all()
        ]

    for job_id in ids:
        try:
            enrich_from_text(job_id)
            done += 1
        except Exception as e:
            print(f"[enrich-all] job {job_id} failed: {e}")
            failed += 1

    return {"enriched": done, "failed": failed}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.fast_api:app", host="0.0.0.0", port=8000, reload=True)


