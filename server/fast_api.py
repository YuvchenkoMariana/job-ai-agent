from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.db.database import Session, JobVacancy, init_db
from backend.ai.enricher import fetch_and_save_text, enrich_from_text
from protocol.python.job import JobDescriptionExtension, JobDescriptionList

if TYPE_CHECKING:
    from backend.db.database import JobVacancy as JobVacancyType


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

@dataclass(frozen=True, slots=True)
class JobDescription(JobDescriptionExtension):
    id: int | None = None
    company_name: str | None = None
    company_overview: str | None = None
    location: str | None = None
    work_type: str | None = None
    role_summary: str | None = None
    responsibilities: str | None = None
    required_quals: str | None = None
    preferred_quals: str | None = None
    tools_and_methods: str | None = None
    what_success_looks: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    language_requirements: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobDescription":
        return cls(
            job_title=str(data["job_title"]),
            source_url=str(data["source_url"]),
            id=int(data["id"]) if data.get("id") is not None else None,
            company_name=data.get("company_name"),
            company_overview=data.get("company_overview"),
            location=data.get("location"),
            work_type=data.get("work_type"),
            role_summary=data.get("role_summary"),
            responsibilities=data.get("responsibilities"),
            required_quals=data.get("required_quals"),
            preferred_quals=data.get("preferred_quals"),
            tools_and_methods=data.get("tools_and_methods"),
            what_success_looks=data.get("what_success_looks"),
            salary_min=data.get("salary_min"),
            salary_max=data.get("salary_max"),
            salary_currency=data.get("salary_currency") or "USD",
            language_requirements=data.get("language_requirements"),
        )

    @classmethod
    def from_row(cls, row: "JobVacancyType") -> "JobDescription":
        return cls(
            id=row.id,
            job_title=row.job_title,
            source_url=row.source_url or "",
            company_name=row.company_name,
            company_overview=row.company_overview,
            location=row.location,
            work_type=row.work_type,
            role_summary=row.role_summary,
            responsibilities=row.responsibilities,
            required_quals=row.required_quals,
            preferred_quals=row.preferred_quals,
            tools_and_methods=row.tools_and_methods,
            what_success_looks=row.what_success_looks,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency or "USD",
            language_requirements=row.language_requirements,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_title": self.job_title,
            "source_url": self.source_url,
            "company_name": self.company_name,
            "company_overview": self.company_overview,
            "location": self.location,
            "work_type": self.work_type,
            "role_summary": self.role_summary,
            "responsibilities": self.responsibilities,
            "required_quals": self.required_quals,
            "preferred_quals": self.preferred_quals,
            "tools_and_methods": self.tools_and_methods,
            "what_success_looks": self.what_success_looks,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "language_requirements": self.language_requirements,
        }

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

    logger.info("sync_jobs called with %d job(s)", len(payload.jobs))

    count = 0
    with Session() as session:
        for item in payload.jobs:
            logger.debug("processing item: job_title=%r, source_url=%r", item.job_title, item.source_url)
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

    logger.info("sync_jobs upserted %d job(s)", count)
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
            logger.error("fetch-text-all job %d failed: %s", job_id, e)
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
            logger.error("enrich-all job %d failed: %s", job_id, e)
            failed += 1

    return {"enriched": done, "failed": failed}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.fast_api:app", host="0.0.0.0", port=8000, reload=True)


