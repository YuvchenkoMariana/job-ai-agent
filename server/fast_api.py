from __future__ import annotations

import concurrent.futures
import logging
import hashlib
import hmac
import json
import os
import queue
import secrets
import threading
from datetime import datetime as _dt, timedelta as _td
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass

from urllib.parse import urlencode
from typing import Any, TYPE_CHECKING
from typing import cast

from sqlalchemy.orm import Session as OrmSession

from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from pydantic import BaseModel

from backend.db.database import (
    Session,
    CvDocument,
    UsersCv,
    User,
    JobPosting,
    JobRun,
    JobRunJob,
    MatchReportCache,
    JobAnalysisCache,
    init_db,
    utc_now_minute,
    GUEST_USER_UUID,
)
from backend.ai.enricher import fetch_and_save_text, enrich_from_text
from backend.ai.cv_classifier import classify_cv
from backend.ai.cv_parser import parse_cv
from backend.ai.matcher import rank_jobs, build_report, analyze_job
from protocol.python.job import JobDescriptionExtension, JobDescriptionList
from server.jobs_sync import upsert_jobs

if TYPE_CHECKING:
    from backend.db.database import JobPosting as JobPostingType


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Background CV-parsing queue
# A single worker thread reads parse jobs from the queue and calls parse_cv.
# Using a queue decouples the slow OpenAI call from the HTTP request.
# The caller blocks on fut.result(timeout=…) — set timeout to 0 for
# fire-and-forget behaviour in the future.
# ---------------------------------------------------------------------------

_cv_parse_queue: "queue.Queue[tuple[concurrent.futures.Future, str] | None]" = queue.Queue()

# Thread reference — created/started inside lifespan, not at import time.
_cv_worker_thread: threading.Thread | None = None


def _cv_worker() -> None:  # pragma: no cover
    while True:
        item = _cv_parse_queue.get()
        if item is None:          # shutdown signal
            _cv_parse_queue.task_done()
            break
        future, text = item
        try:
            if future.set_running_or_notify_cancel():
                result = parse_cv(text)
                future.set_result(result)
        except Exception as exc:
            try:
                future.set_exception(exc)
            except Exception:
                pass
        finally:
            _cv_parse_queue.task_done()


def _ensure_cv_worker_running() -> None:
    """Start the CV-parser worker thread if it is not already running.

    Safe to call multiple times — creates a fresh thread when the previous one
    has stopped (e.g. after a graceful shutdown in tests).
    """
    global _cv_worker_thread
    if _cv_worker_thread is None or not _cv_worker_thread.is_alive():
        _cv_worker_thread = threading.Thread(
            target=_cv_worker, daemon=True, name="cv-parser-worker"
        )
        _cv_worker_thread.start()
        logger.info("CV parser worker thread started")


def _parse_cv_queued(text: str, timeout: float = 120.0):
    """Submit CV text to the background worker and wait for the parsed result.

    The actual parse_cv call runs in the dedicated worker thread, so the
    main event-loop thread is free while waiting.  Set timeout=None to
    wait indefinitely (not recommended for HTTP handlers).
    """
    fut: concurrent.futures.Future = concurrent.futures.Future()
    _cv_parse_queue.put((fut, text))
    return fut.result(timeout=timeout)

_PBKDF2_ITERS = 120_000


def _hash_password(password: str, salt_hex: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        _PBKDF2_ITERS,
    )
    return dk.hex()


def _verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    got = _hash_password(password, salt_hex)
    return hmac.compare_digest(got, expected_hash_hex)


def _new_token() -> str:
    # 32 bytes => 64 hex chars
    return secrets.token_hex(32)


def get_current_user_id(
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> str:
    """Resolve the current user's UUID.

    Backwards compatibility: if no token is provided, we serve the fixed
    GUEST_USER_UUID. This keeps tests + older clients working.
    """

    init_db()
    if not x_auth_token:
        return GUEST_USER_UUID

    with Session() as session:
        u = session.query(User).filter_by(api_token=x_auth_token).first()
        if not u:
            raise HTTPException(status_code=401, detail="Invalid auth token")
        return str(u.id)


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str

@dataclass(frozen=True, slots=True)
class JobDescription(JobDescriptionExtension):
    id: str | None = None
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
            id=str(data["id"]) if data.get("id") is not None else None,
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
    def from_row(cls, row: "JobPostingType") -> "JobDescription":
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
    # ── Startup ──────────────────────────────────────────────────────────────
    # Start the background CV-parsing worker thread.
    # All background resources are initialised here so that running the
    # application (uvicorn server.fast_api:app) is the single entry point
    # that brings everything up.
    _ensure_cv_worker_running()
    init_db()
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────────
    # Send the sentinel value so the worker exits its loop cleanly.
    _cv_parse_queue.put(None)
    if _cv_worker_thread is not None:
        _cv_worker_thread.join(timeout=5)


app = FastAPI(title="Job AI Agent API", version="1.0.0", lifespan=lifespan)

# Serve a tiny client UI (static files) at /ui
_BASE_DIR = Path(__file__).resolve().parent.parent
_UI_DIR = _BASE_DIR / "client"
if _UI_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    """Open the client UI in the browser."""
    # IMPORTANT:
    # We mount static UI files under /ui. The HTML uses relative paths like
    # ./app.js and ./styles.css. If we serve index.html directly at '/', the
    # browser will request '/app.js' and '/styles.css' (404), and the UI won't
    # work. Redirecting to '/ui/' ensures assets are resolved as '/ui/app.js'.
    if _UI_DIR.is_dir():
        return RedirectResponse(url="/ui/")

    # Fallback (should not happen in this repo, but keeps the server robust)
    raise HTTPException(status_code=404, detail="UI directory not found")

app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Auth-Token"],
)


# ---------------------------------------------------------------------------
# Test helper — exposed so tests can reset state between runs
# ---------------------------------------------------------------------------
def _clear_jobs_db(user_id: int = 1) -> None:
    with Session() as session:
        # Tests expect an empty store. We wipe *runs* + global postings.
        session.query(JobRunJob).delete()
        session.query(JobRun).delete()
        session.query(JobAnalysisCache).delete()
        session.query(MatchReportCache).delete()
        session.query(JobPosting).delete()
        session.commit()


def _normalize_text(text: str) -> str:
    # Normalize newlines + trim trailing spaces to make hashing stable.
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return t.strip()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jobs_hash_from_urls(urls: list[str]) -> str:
    uniq = sorted({(u or "").strip() for u in urls if (u or "").strip()})
    return _sha256_hex("\n".join(uniq))


def _jobs_state_hash(session: OrmSession, job_ids: list[str]) -> str:
    # Include job.updated_at so cached analyses invalidate when a posting changes.
    if not job_ids:
        return _sha256_hex("")
    rows = (
        session.query(JobPosting.id, JobPosting.updated_at)
        .filter(JobPosting.id.in_(job_ids))
        .all()
    )
    parts = sorted(f"{str(i)}:{str(ts or '')}" for i, ts in rows)
    return _sha256_hex("\n".join(parts))


def _get_latest_cv(session: OrmSession, *, user_id: str):
    # Use last_used_at to keep 'latest' stable even when CV is deduped.
    # NOTE: SQLAlchemy typing stubs sometimes confuse "instance" vs "type" for
    # declarative models in some IDE checkers; keep this un-annotated to avoid
    # false-positive warnings.
    return (
        session.query(UsersCv)
        .filter(UsersCv.user_id == user_id)
        .order_by((UsersCv.last_used_at.desc()), UsersCv.id.desc())
        .first()
    )


def _get_latest_run(session: OrmSession, *, user_id: str, run_id: str | None = None) -> JobRun | None:
    if run_id is not None:
        run = session.query(JobRun).filter_by(id=str(run_id), user_id=user_id).first()
        return cast(JobRun | None, run)
    run = session.query(JobRun).filter_by(user_id=user_id).order_by(JobRun.id.desc()).first()
    return cast(JobRun | None, run)


def _get_run_job_ids(session: OrmSession, *, run_id: str) -> list[str]:
    rows = session.query(JobRunJob.job_id).filter_by(run_id=run_id).all()
    # rows is a list of 1-tuples: [(job_id,), ...]
    return [str(job_id) for (job_id,) in rows]


def _create_or_reuse_run(
    session: OrmSession,
    *,
    user_id: str,
    cv_id: str | None,
    cv_hash: str | None,
    category: str | None,
    experience_bucket: str | None,
    dou_url: str | None,
    jobs_hash: str,
    job_ids: list[str],
    jobs_found: int | None = None,
    synced: int | None = None,
):
    # Reuse the most recent identical run (same CV + same job set).
    conds = [JobRun.user_id == user_id, JobRun.jobs_hash == jobs_hash]
    if cv_id is None:
        conds.append(JobRun.cv_id.is_(None))
    else:
        conds.append(JobRun.cv_id == str(cv_id))

    existing = session.query(JobRun).filter(*conds).order_by(JobRun.id.desc()).first()
    if existing:
        return existing

    run = JobRun(
        user_id=user_id,
        cv_id=cv_id,
        cv_hash=cv_hash,
        category=category,
        experience_bucket=experience_bucket,
        dou_url=dou_url,
        jobs_hash=jobs_hash,
        jobs_found=jobs_found,
        synced=synced,
        created_at=utc_now_minute(),
    )
    session.add(run)
    session.flush()

    for jid in job_ids:
        session.add(JobRunJob(run_id=str(run.id), job_id=str(jid)))

    return run


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@app.post("/api/auth/register", summary="Register a new user")
def register_user(payload: RegisterRequest) -> dict[str, Any]:
    init_db()

    email = str(payload.email).strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email")
    password = str(payload.password)
    # Minimum password length check intentionally disabled.
    # if len(password) < 6:
    #     raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)

    with Session() as session:
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=409, detail="User with this email already exists")

        token = _new_token()
        u = User(email=email, password_salt=salt, password_hash=pw_hash, api_token=token)
        session.add(u)
        session.commit()
        return {"user_id": str(u.id), "email": u.email, "token": token}


@app.post("/api/auth/login", summary="Login and get an API token")
def login_user(payload: LoginRequest) -> dict[str, Any]:
    init_db()
    email = str(payload.email).strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email")
    password = str(payload.password)

    with Session() as session:
        u = session.query(User).filter(User.email == email).first()
        if not u or not u.password_salt or not u.password_hash:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not _verify_password(password, str(u.password_salt), str(u.password_hash)):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        u.api_token = _new_token()
        session.commit()
        return {"user_id": str(u.id), "email": u.email, "token": str(u.api_token)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post(
    "/api/jobs/sync",
    summary="Push scraped jobs from the plugin",
    response_description="How many jobs were upserted",
)
def sync_jobs(
    payload: JobDescriptionList,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, int]:
    """
    Called by the Chrome extension after it finishes scraping.
    Upserts each job by source_url: insert if new, update title if exists.
    """
    if not payload.jobs:
        raise HTTPException(status_code=422, detail="Payload must not be empty")

    logger.info("sync_jobs called with %d job(s)", len(payload.jobs))
    # Auth is optional: if the client doesn't send X-Auth-Token, the dependency
    # returns the guest user_id=1.
    job_ids = upsert_jobs(payload)
    urls = [j.source_url or "" for j in payload.jobs]
    jobs_hash = _jobs_hash_from_urls(urls)

    with Session() as session:
        _create_or_reuse_run(
            session,
            user_id=user_id,
            cv_id=None,
            cv_hash=None,
            category=None,
            experience_bucket=None,
            dou_url=None,
            jobs_hash=jobs_hash,
            job_ids=job_ids,
            jobs_found=len(payload.jobs),
            synced=len(job_ids),
        )
        session.commit()

    return {"count": int(len(job_ids))}


@app.get(
    "/api/jobs",
    summary="Get all job descriptions from the database",
)
def get_jobs(
    run_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> list[dict]:
    """Return job descriptions.

    Backwards-compatible behavior:
    - if run_id is provided: return jobs for that specific run snapshot
    - if run_id is not provided: return the union of all jobs ever synced/scraped
      for this user (across runs)
    """
    with Session() as session:
        job_ids: list[int]

        if run_id is not None:
            run = _get_latest_run(session, user_id=user_id, run_id=run_id)
            if not run:
                return []
            job_ids = _get_run_job_ids(session, run_id=str(run.id))
        else:
            # Union of jobs across all runs for this user.
            rows = (
                session.query(JobRunJob.job_id)
                .join(JobRun, JobRun.id == JobRunJob.run_id)
                .filter(JobRun.user_id == user_id)
                .all()
            )
            job_ids = [str(job_id) for (job_id,) in rows]
            # de-dup while keeping deterministic ordering
            job_ids = sorted(set(job_ids))

        if not job_ids:
            return []

        rows = session.query(JobPosting).filter(JobPosting.id.in_(job_ids)).order_by(JobPosting.id).all()
        return JobDescriptionList(jobs=[JobDescription.from_row(r) for r in rows]).to_list()


# ---------------------------------------------------------------------------
# CV upload (raw document) — for the client UI
# ---------------------------------------------------------------------------


@app.post(
    "/api/cv/upload",
    summary="Upload a CV file (raw text) and store it in the database",
)
async def upload_cv(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, int | str]:
    """Accept a text/markdown CV file and store its contents in cv_documents."""
    # Ensure tables exist even when the app is used without lifespan startup
    # (e.g., in certain test/client contexts).
    init_db()

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback that won't crash on Windows-encoded text.
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    norm = _normalize_text(text)
    cv_hash = _sha256_hex(norm)

    with Session() as session:
        # Raw document de-dup (per-user)
        doc = (
            session.query(CvDocument)
            .filter(CvDocument.user_id == user_id, CvDocument.content_hash == cv_hash)
            .first()
        )
        if not doc:
            doc = CvDocument(
                filename=file.filename,
                content_text=norm,
                content_hash=cv_hash,
                user_id=user_id,
            )
            session.add(doc)
            session.flush()

        # Structured CV de-dup (per-user)
        user_cv = (
            session.query(UsersCv)
            .filter(UsersCv.user_id == user_id, UsersCv.cv_hash == cv_hash)
            .first()
        )
        if not user_cv:
            parsed = parse_cv(norm)
            user_cv = UsersCv(
                **parsed.to_sa_kwargs(),
                user_id=user_id,
                cv_hash=cv_hash,
                last_used_at=utc_now_minute(),
            )
            session.add(user_cv)
            session.flush()
        else:
            user_cv.last_used_at = utc_now_minute()

        session.commit()
        return {
            "id": str(doc.id),
            "filename": doc.filename or "",
            "chars": len(doc.content_text or ""),
            "cv_hash": cv_hash,
            # new naming
            "user_cv_id": str(user_cv.id),
            # backwards compatibility for old clients
            "my_cv_id": str(user_cv.id),
            "job_title": user_cv.job_title,
        }


@app.post(
    "/api/cv/run",
    summary="Upload a CV, detect category, scrape DOU, and store a run snapshot",
)
async def upload_cv_and_scrape(
    file: UploadFile = File(...),
    headless: bool = True,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Main 'one button' flow for the UI.

    Steps:
    1) De-dup and store CV (cv_documents + users_cv)
    2) Detect DOU category from CV
    3) Scrape DOU вакансії for that category via Selenium
    4) Store the job set as a *run* snapshot (history)
    """
    # 1) Upload CV (de-dup)
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    norm = _normalize_text(text)
    cv_hash = _sha256_hex(norm)

    with Session() as session:
        # Raw doc de-dup
        doc = (
            session.query(CvDocument)
            .filter(CvDocument.user_id == user_id, CvDocument.content_hash == cv_hash)
            .first()
        )
        if not doc:
            doc = CvDocument(filename=file.filename, content_text=norm, content_hash=cv_hash, user_id=user_id)
            session.add(doc)
            session.flush()

        # Structured CV de-dup
        user_cv = (
            session.query(UsersCv)
            .filter(UsersCv.user_id == user_id, UsersCv.cv_hash == cv_hash)
            .first()
        )
        parsed = None
        if not user_cv:
            parsed = _parse_cv_queued(norm)
            user_cv = UsersCv(
                **parsed.to_sa_kwargs(),
                user_id=user_id,
                cv_hash=cv_hash,
                last_used_at=utc_now_minute(),
            )
            session.add(user_cv)
            session.flush()
        else:
            user_cv.last_used_at = utc_now_minute()

        # If CV already existed, avoid re-parsing (may cost OpenAI tokens).
        if parsed is None:
            # minimal ParsedCv-like fields used below
            class _Parsed:
                job_title = user_cv.job_title
                years_experience = user_cv.years_experience
                experience_bucket = user_cv.experience_bucket

            parsed = _Parsed()

        session.commit()
        user_cv_id = str(user_cv.id)

    # 2) Classify category
    cls = classify_cv((getattr(parsed, "job_title", None) or "") or norm)
    params: dict[str, str] = {"category": cls.category}
    if getattr(parsed, "experience_bucket", None):
        params["exp"] = str(getattr(parsed, "experience_bucket"))
    dou_url = "https://jobs.dou.ua/vacancies/?" + urlencode(params)

    # ── Smart run reuse ──────────────────────────────────────────────────
    # If the same CV + same category was processed recently, skip Selenium
    # and return the cached run. Threshold: REUSE_RUN_MAX_AGE_HOURS (default 4h).
    reuse_hours = float(os.getenv("REUSE_RUN_MAX_AGE_HOURS", "4"))
    if reuse_hours > 0:
        with Session() as session:
            recent_run = (
                session.query(JobRun)
                .filter(
                    JobRun.user_id == user_id,
                    JobRun.cv_hash == cv_hash,
                    JobRun.category == cls.category,
                )
                .order_by(JobRun.id.desc())
                .first()
            )
            if recent_run and recent_run.created_at:
                age = _dt.utcnow() - recent_run.created_at
                if age < _td(hours=reuse_hours):
                    job_ids_for_run = _get_run_job_ids(session, run_id=str(recent_run.id))
                    return {
                        "run_id": str(recent_run.id),
                        "user_cv_id": user_cv_id,
                        "cv_hash": cv_hash,
                        "job_title": getattr(parsed, "job_title", None),
                        "years_experience": getattr(parsed, "years_experience", None),
                        "experience_bucket": getattr(parsed, "experience_bucket", None),
                        "category": cls.category,
                        "dou_url": recent_run.dou_url or dou_url,
                        "reused": True,
                        "reused_age_hours": round(age.total_seconds() / 3600, 1),
                        "scrape": {
                            "clicks": 0,
                            "jobs_found": recent_run.jobs_found or len(job_ids_for_run),
                            "synced": 0,
                        },
                    }

    # 3) Scrape DOU вакансії and sync into the global catalog
    try:
        # Local import to avoid any import-time Selenium side effects
        from server.scraper import scrape_and_sync

        scrape_res = scrape_and_sync(dou_url, headless=headless, user_id=user_id)

        # 4) Store run snapshot (history). jobs_hash includes job.updated_at for cache invalidation.
        with Session() as session:
            jobs_hash = _jobs_state_hash(session, scrape_res.job_ids)
            run = _create_or_reuse_run(
                session,
                user_id=user_id,
                cv_id=user_cv_id,
                cv_hash=cv_hash,
                category=cls.category,
                experience_bucket=getattr(parsed, "experience_bucket", None),
                dou_url=dou_url,
                jobs_hash=jobs_hash,
                job_ids=scrape_res.job_ids,
                jobs_found=int(scrape_res.jobs_found),
                synced=int(scrape_res.synced),
            )
            session.commit()
            # Capture the PK *inside* the session before it closes —
            # accessing ORM attributes on a detached instance triggers a refresh
            # that fails because the session is gone.
            run_id = str(run.id)

        return {
            "run_id": run_id,
            "user_cv_id": user_cv_id,
            "cv_hash": cv_hash,
            "job_title": getattr(parsed, "job_title", None),
            "years_experience": getattr(parsed, "years_experience", None),
            "experience_bucket": getattr(parsed, "experience_bucket", None),
            "category": cls.category,
            "dou_url": dou_url,
            "scrape": {
                "clicks": int(scrape_res.clicks),
                "jobs_found": int(scrape_res.jobs_found),
                "synced": int(scrape_res.synced),
            },
        }
    except Exception as e:
        # CV is already stored; give a clear error for Selenium issues.
        raise HTTPException(
            status_code=500,
            detail=(
                "CV uploaded, but scraping DOU failed. "
                "Make sure Google Chrome is installed and Selenium can start it. "
                f"Error: {e}"
            ),
        )


@app.get(
    "/api/cv/latest",
    summary="Get the latest uploaded CV document (metadata)",
)
def get_latest_cv(user_id: str = Depends(get_current_user_id)) -> dict[str, int | str] | None:
    init_db()
    with Session() as session:
        doc = (
            session.query(CvDocument)
            .filter(CvDocument.user_id == user_id)
            .order_by(CvDocument.id.desc())
            .first()
        )
        if not doc:
            return None
        return {
            "id": str(doc.id),
            "filename": doc.filename or "",
            "chars": len(doc.content_text or ""),
        }


def _latest_users_cv_payload(cv: Any) -> dict[str, Any]:
    return {
        "id": str(cv.id),
        "job_title": cv.job_title,
        "all_text_chars": len(cv.all_text or ""),
        "years_experience": cv.years_experience,
        "experience_bucket": cv.experience_bucket,
        "full_name": cv.full_name,
        "email": cv.email,
        "phone": cv.phone,
        "location": cv.location,
        "github_url": cv.github_url,
        "linkedin_url": cv.linkedin_url,
        "profile_summary": cv.profile_summary,
        "programming_skills": cv.programming_skills,
        "tools_and_tech": cv.tools_and_tech,
        "other_skills": cv.other_skills,
        "projects": cv.projects,
        "education": cv.education,
        "career_objective": cv.career_objective,
        "additional_info": cv.additional_info,
    }


@app.get(
    "/api/users-cv/latest",
    summary="Get latest structured CV (users_cv)",
)
def get_latest_users_cv(user_id: str = Depends(get_current_user_id)) -> dict[str, Any] | None:
    init_db()
    with Session() as session:
        cv = _get_latest_cv(session, user_id=user_id)
        if not cv:
            return None
        return _latest_users_cv_payload(cv)


# Backwards-compatible route
@app.get(
    "/api/my-cv/latest",
    include_in_schema=False,
)
def get_latest_my_cv(user_id: int = Depends(get_current_user_id)) -> dict[str, Any] | None:
    return get_latest_users_cv(user_id=user_id)


# ---------------------------------------------------------------------------
# Match scoring + report (CV ↔ jobs)
# ---------------------------------------------------------------------------


@app.get(
    "/api/match/scores",
    summary="Rank all jobs in DB by match score against the latest uploaded CV",
)
def get_match_scores(
    limit: int = 50,
    run_id: str | None = None,
    cv_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    init_db()
    with Session() as session:
        if cv_id is not None:
            cv = session.query(UsersCv).filter_by(id=str(cv_id), user_id=user_id).first()
        else:
            cv = _get_latest_cv(session, user_id=user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="No uploaded CV found")

        run = _get_latest_run(session, user_id=user_id, run_id=run_id)
        if not run:
            raise HTTPException(status_code=404, detail="No jobs found — run scraping first")

        job_ids = _get_run_job_ids(session, run_id=str(run.id))
        jobs = session.query(JobPosting).filter(JobPosting.id.in_(job_ids)).order_by(JobPosting.id).all()

    ranked = rank_jobs(cv, jobs, limit=limit)
    return {
        "cv_id": str(cv.id),
        "run_id": str(run.id),
        "total_jobs": len(jobs),
        "items": [i.to_dict() for i in ranked],
    }


@app.get(
    "/api/match/report",
    summary="Get an overall match report (heuristic by default, OpenAI optional)",
)
def get_match_report(
    top_n: int = 10,
    run_id: str | None = None,
    cv_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    init_db()
    with Session() as session:
        if cv_id is not None:
            cv = session.query(UsersCv).filter_by(id=str(cv_id), user_id=user_id).first()
        else:
            cv = _get_latest_cv(session, user_id=user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="No uploaded CV found")

        run = _get_latest_run(session, user_id=user_id, run_id=run_id)
        if not run:
            raise HTTPException(status_code=404, detail="No jobs found — run scraping first")

        job_ids = _get_run_job_ids(session, run_id=str(run.id))
        jobs = session.query(JobPosting).filter(JobPosting.id.in_(job_ids)).order_by(JobPosting.id).all()

        jobs_hash = _jobs_state_hash(session, job_ids)

        preferred_method = "openai" if (os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MATCHER", "0") == "1") else "heuristic"
        cached = (
            session.query(MatchReportCache)
            .filter_by(
                user_id=user_id,
                cv_id=str(cv.id),
                jobs_hash=jobs_hash,
                top_n=int(top_n),
                method=preferred_method,
            )
            .order_by(MatchReportCache.id.desc())
            .first()
        )
        if cached and cached.payload_json:
            try:
                data = json.loads(cached.payload_json)
                data.update({"cv_id": str(cv.id), "run_id": str(run.id), "total_jobs": len(jobs)})
                return data
            except Exception:
                pass

    ranked = rank_jobs(cv, jobs)
    jobs_by_id = {str(j.id): j for j in jobs}
    report = build_report(cv, ranked, jobs_by_id, top_n=top_n)

    # Cache report (as JSON)
    try:
        with Session() as session:
            session.add(
                MatchReportCache(
                    user_id=user_id,
                    cv_id=str(cv.id),
                    jobs_hash=jobs_hash,
                    top_n=int(top_n),
                    method=str(report.get("method") or "heuristic"),
                    summary=str(report.get("summary") or ""),
                    payload_json=json.dumps(report, ensure_ascii=False),
                    created_at=utc_now_minute(),
                )
            )
            session.commit()
    except Exception:
        pass

    report.update({"cv_id": str(cv.id), "run_id": str(run.id), "total_jobs": len(jobs)})
    return report


@app.get(
    "/api/match/job/{job_id}/analysis",
    summary="Get a focused CV↔job analysis for one vacancy (OpenAI optional)",
)
def get_match_job_analysis(
    job_id: str,
    run_id: str | None = None,
    cv_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    init_db()
    with Session() as session:
        # If a run_id is provided, prefer the CV used in that run.
        if cv_id is None and run_id is not None:
            run = _get_latest_run(session, user_id=user_id, run_id=run_id)
            if run and run.cv_id is not None:
                cv_id = str(run.cv_id)

        if cv_id is not None:
            cv = session.query(UsersCv).filter_by(id=str(cv_id), user_id=user_id).first()
        else:
            cv = _get_latest_cv(session, user_id=user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="No uploaded CV found")

        job = session.query(JobPosting).filter_by(id=str(job_id)).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

        preferred_method = "openai" if (os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MATCHER", "0") == "1") else "heuristic"
        cached = (
            session.query(JobAnalysisCache)
            .filter_by(
                user_id=user_id,
                cv_id=str(cv.id),
                job_id=str(job_id),
                job_updated_at=job.updated_at,
                method=preferred_method,
            )
            .order_by(JobAnalysisCache.id.desc())
            .first()
        )
        if cached and cached.payload_json:
            try:
                data = json.loads(cached.payload_json)
                data["job"] = {
                    "id": str(job.id),
                    "job_title": job.job_title,
                    "source_url": job.source_url,
                    "company_name": job.company_name,
                }
                data["cv_id"] = str(cv.id)
                return data
            except Exception:
                pass

    data = analyze_job(cv, job)
    # include basic job info for UI
    data["job"] = {
        "id": str(job.id),
        "job_title": job.job_title,
        "source_url": job.source_url,
        "company_name": job.company_name,
    }
    data["cv_id"] = str(cv.id)

    # Best-effort cache
    try:
        with Session() as session:
            session.add(
                JobAnalysisCache(
                    user_id=user_id,
                    cv_id=str(cv.id),
                    job_id=str(job.id),
                    job_updated_at=job.updated_at,
                    method=str(data.get("method") or "heuristic"),
                    score=float(data.get("score") or 0.0),
                    summary=str(data.get("summary") or ""),
                    reasons_json=json.dumps(data.get("reasons") or [], ensure_ascii=False),
                    html=str(data.get("html") or ""),
                    markdown=str(data.get("markdown") or ""),
                    payload_json=json.dumps(data, ensure_ascii=False),
                    created_at=utc_now_minute(),
                )
            )
            session.commit()
    except Exception:
        pass

    return data


# ---------------------------------------------------------------------------
# History (previous runs / analyses)
# ---------------------------------------------------------------------------


@app.get(
    "/api/history/runs",
    summary="List previous run snapshots for the current user",
)
def list_runs(limit: int = 20, user_id: str = Depends(get_current_user_id)) -> list[dict[str, Any]]:
    init_db()
    lim = max(1, min(200, int(limit)))
    with Session() as session:
        runs = (
            session.query(JobRun)
            .filter(JobRun.user_id == user_id)
            .order_by(JobRun.id.desc())
            .limit(lim)
            .all()
        )

        # batch-load CV titles
        cv_ids = sorted({str(r.cv_id) for r in runs if r.cv_id is not None})
        cvs_by_id: dict[str, UsersCv] = {}
        if cv_ids:
            for cv in session.query(UsersCv).filter(UsersCv.id.in_(cv_ids), UsersCv.user_id == user_id).all():
                cvs_by_id[str(cv.id)] = cv

        out: list[dict[str, Any]] = []
        for r in runs:
            cv_title = None
            if r.cv_id is not None:
                cv = cvs_by_id.get(str(r.cv_id))
                if cv:
                    cv_title = cv.job_title
            out.append(
                {
                    "run_id": str(r.id),
                    "created_at": str(r.created_at or ""),
                    "cv_id": str(r.cv_id) if r.cv_id is not None else None,
                    "cv_job_title": cv_title,
                    "category": r.category,
                    "experience_bucket": r.experience_bucket,
                    "jobs_found": r.jobs_found,
                    "synced": r.synced,
                    "dou_url": r.dou_url,
                }
            )
        return out


# ---------------------------------------------------------------------------
# Plugin helper: determine DOU category URL from uploaded CV
# ---------------------------------------------------------------------------


@app.get(
    "/api/plugin/dou-target",
    summary="Get a DOU vacancies URL based on the latest uploaded CV",
)
def get_dou_target_from_latest_cv(user_id: str = Depends(get_current_user_id)) -> dict[str, str | float | None]:
    """Return the URL the plugin should use to search for vacancies.

    Prefer the latest *structured* CV row in `users_cv` (because it contains many
    fields). If none exists, fall back to the latest uploaded raw CV document.
    """
    init_db()
    with Session() as session:
        cv = _get_latest_cv(session, user_id=user_id)
        if cv and (cv.job_title or "").strip():
            cls = classify_cv(cv.job_title)
        else:
            doc = (
                session.query(CvDocument)
                .filter(CvDocument.user_id == user_id)
                .order_by(CvDocument.id.desc())
                .first()
            )
            if not doc or not (doc.content_text or "").strip():
                raise HTTPException(status_code=404, detail="No uploaded CV found")
            cls = classify_cv(doc.content_text)

        params: dict[str, str] = {"category": cls.category}
        exp: str | None = None
        if cv is not None and cv.experience_bucket:
            exp = str(cv.experience_bucket)
        if exp is not None:
            params["exp"] = exp

        url = "https://jobs.dou.ua/vacancies/?" + urlencode(params)
        return {
            "category": cls.category,
            "dou_url": url,
            "job_title": (cv.job_title if cv else cls.job_title),
            "confidence": cls.confidence,
            "method": cls.method,
            "years_experience": (cv.years_experience if cv else None),
            "experience_bucket": exp,
        }


@app.get(
    "/api/plugin/dou-target/redirect",
    include_in_schema=False,
)
def redirect_to_dou_target(user_id: int = Depends(get_current_user_id)):
    """Convenience redirect for manual testing in a browser."""
    from fastapi.responses import RedirectResponse

    data = get_dou_target_from_latest_cv(user_id=user_id)
    return RedirectResponse(url=str(data["dou_url"]))


# ---------------------------------------------------------------------------
# AI enrichment — Step 2 + Step 3
# ---------------------------------------------------------------------------

@app.post(
    "/api/jobs/{job_id}/fetch-text",
    summary="Step 2 — fetch job page and save full text to DB",
)
def fetch_text_one(job_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, int]:
    """Fetches source_url for job_id and stores the raw page text in full_text."""
    try:
        text = fetch_and_save_text(job_id, user_id=user_id)
        return {"job_id": job_id, "chars": len(text)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/api/jobs/fetch-text-all",
    summary="Step 2 for all jobs — fetch page text for every job without full_text",
)
def fetch_text_all(user_id: str = Depends(get_current_user_id)) -> dict[str, int]:
    """Fetches and saves page text for all jobs where full_text is still null."""
    done, failed = 0, 0
    with Session() as session:
        run = _get_latest_run(session, user_id=user_id)
        if not run:
            return {"done": 0, "failed": 0}
        job_ids = _get_run_job_ids(session, run_id=str(run.id))
        ids = [
            str(j.id)
            for j in session.query(JobPosting).filter(
                JobPosting.id.in_(job_ids),
                JobPosting.full_text.is_(None),
                JobPosting.source_url.isnot(None),
            ).all()
        ]

    for job_id in ids:
        try:
            fetch_and_save_text(job_id, user_id=user_id)
            done += 1
        except Exception as e:
            logger.error("fetch-text-all job %d failed: %s", job_id, e)
            failed += 1

    return {"done": done, "failed": failed}


@app.post(
    "/api/jobs/{job_id}/enrich",
    summary="Step 3 — read full_text from DB and fill fields using OpenAI",
)
def enrich_one(job_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    """Reads full_text for job_id, calls OpenAI, saves structured fields to DB."""
    try:
        return enrich_from_text(job_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post(
    "/api/jobs/enrich-all",
    summary="Step 3 for all jobs — enrich every job that has full_text but no role_summary",
)
def enrich_all(user_id: str = Depends(get_current_user_id)) -> dict[str, int]:
    """Enriches all jobs that have full_text but not yet a role_summary."""
    done, failed = 0, 0
    with Session() as session:
        run = _get_latest_run(session, user_id=user_id)
        if not run:
            return {"enriched": 0, "failed": 0}
        job_ids = _get_run_job_ids(session, run_id=str(run.id))
        ids = [
            str(j.id)
            for j in session.query(JobPosting).filter(
                JobPosting.id.in_(job_ids),
                JobPosting.full_text.isnot(None),
                JobPosting.role_summary.is_(None),
            ).all()
        ]

    for job_id in ids:
        try:
            enrich_from_text(job_id, user_id=user_id)
            done += 1
        except Exception as e:
            logger.error("enrich-all job %d failed: %s", job_id, e)
            failed += 1

    return {"enriched": done, "failed": failed}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.fast_api:app", host="0.0.0.0", port=8000, reload=True)


