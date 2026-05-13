"""
database.py — SQLAlchemy models for Jobs Search project.

Tables
──────
  users_cv      → stores user's CV split into semantic blocks (renamed from my_cv)
  job_vacancies → stores scraped / pasted job listings split into blocks
"""

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import uuid
from typing import cast

# Timestamp policy
# ----------------
# Store all timestamps in UTC.
#
# SQLite doesn't have a dedicated datetime storage class; SQLAlchemy will persist
# Python datetimes as strings. To avoid microsecond noise and keep things stable,
# we truncate to minutes.


def utc_now_minute() -> datetime:
    """UTC time truncated to minutes (no seconds/microseconds).

    Returned as a naive datetime so SQLite stores a clean "YYYY-MM-DD HH:MM:00"
    style value (without timezone suffix).
    """
    return datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)


def format_utc_naive_in_tz(dt: datetime | None, tz_name: str, fmt: str = "%Y-%m-%d %H:%M") -> str | None:
    """Format a UTC timestamp (stored as naive datetime) in another timezone.

    This implements the pattern you described:

        utc_dt = row.created_at.replace(tzinfo=timezone.utc)
        la_dt = utc_dt.astimezone(ZoneInfo("America/Los_Angeles"))
        la_dt.strftime("%Y-%m-%d %H:%M")

    We keep storage in UTC, and only convert for display.
    """
    if dt is None:
        return None
    utc_dt = dt.replace(tzinfo=timezone.utc)
    local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
    return local_dt.strftime(fmt)

# ── Engine ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "jobs_search.db")

# Tests set DB_URL=sqlite:///:memory: via conftest.py — production uses the file
_db_url = os.getenv("DB_URL", f"sqlite:///{DB_PATH}")

if _db_url == "sqlite:///:memory:":
    # StaticPool keeps a single shared connection so all sessions see the same data
    engine = create_engine(
        _db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(_db_url, echo=False)

Session = sessionmaker(bind=engine)


# ── Base ──────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Guest user identity ───────────────────────────────────────────────────────
# A fixed UUID-format ID for the backwards-compatible "guest" account.
# Every unauthenticated request is served as this user.
GUEST_USER_UUID: str = "00000000-0000-0000-0000-000000000001"


# ── Table 0: users ────────────────────────────────────────────────────────────
class User(Base):
    """Application user.

    This project intentionally keeps auth simple (token + password hash) because
    it is a local/offline-first tool.

    We still store a proper PBKDF2 hash (see server.fast_api) rather than plain
    text.
    """

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(200), nullable=False, unique=True, index=True)

    # PBKDF2 fields
    password_salt = Column(String(64), nullable=True)
    password_hash = Column(String(128), nullable=True)

    # A simple API token for the browser UI / extension.
    api_token = Column(String(64), nullable=True, unique=True, index=True)

    created_at = Column(DateTime, default=utc_now_minute)
    updated_at = Column(DateTime, default=utc_now_minute, onupdate=utc_now_minute)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email='{self.email}'>"


# ── Table 1: users_cv (formerly my_cv) ───────────────────────────────────────
class UsersCv(Base):
    """
    Represents YOUR CV split into logical blocks.

    Fields mirror the standard CV structure:
      job_title            – target role / position you apply for
      full_name            – your full name
      email                – contact e-mail
      phone                – contact phone
      location             – city / country + relocation note
      github_url           – GitHub profile link
      linkedin_url         – LinkedIn profile link
      profile_summary      – short personal intro / about-me paragraph
      programming_skills   – languages, frameworks, paradigms (comma-separated)
      tools_and_tech       – dev tools, IDEs, platforms (comma-separated)
      other_skills         – soft skills, methodologies, languages (comma-sep.)
      projects             – JSON-style or plain-text list of portfolio projects
      education            – university, degree, years
      career_objective     – what kind of role / growth you seek
      additional_info      – relocation availability, extra notes
      created_at           – record creation timestamp
      updated_at           – last update timestamp
    """
    __tablename__ = "users_cv"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Multi-user support: scope CVs to a user.
    user_id             = Column(String(36), nullable=False, default=GUEST_USER_UUID, index=True)

    # De-dup key: sha256(normalized CV text). We keep one structured CV per user per hash.
    cv_hash             = Column(String(64), nullable=True, index=True)

    # Helps determine the 'latest' CV even when the user uploads the same file again.
    last_used_at        = Column(DateTime, nullable=True)

    # ── Position ──────────────────────────────────────────────────────────────
    job_title           = Column(String(200), nullable=False)          # e.g. "Python Developer (Entry Level)"
    # ── Contact ───────────────────────────────────────────────────────────────
    full_name           = Column(String(200),  nullable=True)
    email               = Column(String(200),  nullable=True)
    phone               = Column(String(50),   nullable=True)
    location            = Column(String(300),  nullable=True)
    github_url          = Column(String(300),  nullable=True)
    linkedin_url        = Column(String(300),  nullable=True)

    # ── Content blocks ────────────────────────────────────────────────────────
    # Raw uploaded CV text (the source of truth)
    all_text            = Column(Text, nullable=False, default="")

    # Experience extracted from CV (used for DOU exp filter)
    years_experience    = Column(Float, nullable=True)
    # One of: 0-1, 1-3, 3-5, 5plus (DOU-compatible)
    experience_bucket   = Column(String(20), nullable=True)

    profile_summary     = Column(Text, nullable=True)                   # "About me" paragraph
    programming_skills  = Column(Text, nullable=True)                   # Python, Flask, Django, REST…
    tools_and_tech      = Column(Text, nullable=True)                   # Git, Docker, Postman, Linux…
    other_skills        = Column(Text, nullable=True)                   # English B2, Agile, DSA…
    projects            = Column(Text, nullable=True)                   # list of projects + descriptions
    education           = Column(Text, nullable=True)                   # university, field, years
    career_objective    = Column(Text, nullable=True)                   # what role you want
    additional_info     = Column(Text, nullable=True)                   # relocation, misc notes

    # ── Meta ──────────────────────────────────────────────────────────────────
    created_at          = Column(DateTime, default=utc_now_minute)
    updated_at          = Column(DateTime, default=utc_now_minute, onupdate=utc_now_minute)

    def __repr__(self) -> str:
        return f"<UsersCv id={self.id} job_title='{self.job_title}' name='{self.full_name}'>"

    # Display helpers (DST-correct)
    @property
    def created_at_los_angeles(self) -> str | None:
        return format_utc_naive_in_tz(cast(datetime | None, cast(object, self.created_at)), "America/Los_Angeles")

    @property
    def updated_at_los_angeles(self) -> str | None:
        return format_utc_naive_in_tz(cast(datetime | None, cast(object, self.updated_at)), "America/Los_Angeles")


# ── Table 2: job_vacancies ────────────────────────────────────────────────────
class JobVacancy(Base):
    """
    Represents a job listing split into standard blocks.

    Fields mirror the generic job description template:
      job_title            – role name (e.g. "Python Backend Developer")
      company_name         – hiring company
      company_overview     – short company description
      location             – city / remote / hybrid
      work_type            – Full-time / Part-time / Contract / Remote
      role_summary         – high-level description of the role
      responsibilities     – key duties (free text or bullet list)
      required_quals       – must-have education, experience, skills
      preferred_quals      – nice-to-have skills / bonus experience
      tools_and_methods    – tech stack, tools, frameworks required
      what_success_looks   – measurable outcomes / KPIs for the role
      salary_min           – lower bound of salary range (numeric)
      salary_max           – upper bound of salary range (numeric)
      salary_currency      – USD / UAH / EUR …
      benefits             – health, PTO, stock, etc. (free text)
      how_to_apply         – application instructions
      source_url           – URL where the vacancy was found
      language_requirements– e.g. "English B2, Ukrainian Native"
      created_at           – when the record was added
      updated_at           – last update timestamp
    """
    __tablename__ = "job_vacancies"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Multi-user support: scope vacancies to a user.
    user_id             = Column(String(36), nullable=False, default=GUEST_USER_UUID, index=True)

    # ── Core identity ─────────────────────────────────────────────────────────
    job_title           = Column(String(200), nullable=False)
    company_name        = Column(String(200), nullable=True)
    company_overview    = Column(Text,        nullable=True)

    # ── Location & type ───────────────────────────────────────────────────────
    location            = Column(String(300), nullable=True)
    work_type           = Column(String(100), nullable=True)            # In-person / Remote / Hybrid

    # ── Description blocks ────────────────────────────────────────────────────
    role_summary        = Column(Text, nullable=True)
    responsibilities    = Column(Text, nullable=True)
    required_quals      = Column(Text, nullable=True)
    preferred_quals     = Column(Text, nullable=True)
    tools_and_methods   = Column(Text, nullable=True)
    what_success_looks  = Column(Text, nullable=True)

    # ── Compensation ──────────────────────────────────────────────────────────
    salary_min          = Column(Integer,     nullable=True)
    salary_max          = Column(Integer,     nullable=True)
    salary_currency     = Column(String(10),  nullable=True, default="USD")

    # ── Application ───────────────────────────────────────────────────────────
    source_url          = Column(String(500), nullable=True)
    language_requirements = Column(String(300), nullable=True)

    # ── Raw page content (filled by step 2) ───────────────────────────────────
    full_text           = Column(Text, nullable=True)

    # ── Meta ──────────────────────────────────────────────────────────────────
    created_at          = Column(DateTime, default=utc_now_minute)
    updated_at          = Column(DateTime, default=utc_now_minute, onupdate=utc_now_minute)

    def __repr__(self) -> str:
        return f"<JobVacancy id={self.id} title='{self.job_title}' company='{self.company_name}'>"

    # Display helpers (DST-correct)
    @property
    def created_at_los_angeles(self) -> str | None:
        return format_utc_naive_in_tz(cast(datetime | None, cast(object, self.created_at)), "America/Los_Angeles")

    @property
    def updated_at_los_angeles(self) -> str | None:
        return format_utc_naive_in_tz(cast(datetime | None, cast(object, self.updated_at)), "America/Los_Angeles")


# ── Table 3: cv_documents ─────────────────────────────────────────────────────
class CvDocument(Base):
    """Raw CV documents uploaded by the user.

    We keep this separate from `users_cv` (which is the *structured* CV).
    This table stores the raw uploaded text so the UI can upload a CV file even
    before you build parsing/enrichment.
    """

    __tablename__ = "cv_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Multi-user support: scope documents to a user.
    user_id = Column(String(36), nullable=False, default=GUEST_USER_UUID, index=True)
    filename = Column(String(300), nullable=True)
    content_text = Column(Text, nullable=False)

    # De-dup key: sha256(normalized raw text)
    content_hash = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime, default=utc_now_minute)
    updated_at = Column(DateTime, default=utc_now_minute, onupdate=utc_now_minute)


# ── Global job catalog + per-user runs ────────────────────────────────────────


class JobPosting(Base):
    """A global catalog of vacancies (stored once, reused across users and runs)."""

    __tablename__ = "job_postings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    source_url = Column(String(500), nullable=False, unique=True, index=True)
    job_title = Column(String(200), nullable=False)

    company_name = Column(String(200), nullable=True)
    company_overview = Column(Text, nullable=True)
    location = Column(String(300), nullable=True)
    work_type = Column(String(100), nullable=True)
    role_summary = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    required_quals = Column(Text, nullable=True)
    preferred_quals = Column(Text, nullable=True)
    tools_and_methods = Column(Text, nullable=True)
    what_success_looks = Column(Text, nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(10), nullable=True, default="USD")
    language_requirements = Column(String(300), nullable=True)
    full_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now_minute)
    updated_at = Column(DateTime, default=utc_now_minute, onupdate=utc_now_minute)


class JobRun(Base):
    """A user's 'run' (a snapshot of what jobs were relevant at that moment)."""

    __tablename__ = "job_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    cv_id = Column(String(36), nullable=True, index=True)
    cv_hash = Column(String(64), nullable=True, index=True)
    category = Column(String(100), nullable=True)
    experience_bucket = Column(String(20), nullable=True)
    dou_url = Column(String(700), nullable=True)
    jobs_hash = Column(String(64), nullable=False, index=True)
    jobs_found = Column(Integer, nullable=True)
    synced = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utc_now_minute, index=True)


class JobRunJob(Base):
    """Many-to-many mapping: which jobs belong to a run."""

    __tablename__ = "job_run_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), nullable=False, index=True)
    job_id = Column(String(36), nullable=False, index=True)


class MatchReportCache(Base):
    """Cached overall match report."""

    __tablename__ = "match_report_cache"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    cv_id = Column(String(36), nullable=False, index=True)
    jobs_hash = Column(String(64), nullable=False, index=True)
    top_n = Column(Integer, nullable=False, default=10)
    method = Column(String(20), nullable=False, default="heuristic")
    summary = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_minute, index=True)


class JobAnalysisCache(Base):
    """Cached CV↔Job analysis (per job)."""

    __tablename__ = "job_analysis_cache"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    cv_id = Column(String(36), nullable=False, index=True)
    job_id = Column(String(36), nullable=False, index=True)
    job_updated_at = Column(DateTime, nullable=True)
    method = Column(String(20), nullable=False, default="heuristic")
    score = Column(Float, nullable=True)
    summary = Column(Text, nullable=True)
    reasons_json = Column(Text, nullable=True)
    html = Column(Text, nullable=True)
    markdown = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_minute, index=True)


# ── Init helpers ──────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables (safe to call multiple times — skips existing).

    Migration: if the DB has old integer-PK tables, drops them all so that
    create_all can rebuild with UUID-based PKs.
    """

    # ── UUID migration ────────────────────────────────────────────────────────
    # Detect old integer-PK schema (users.id column type = INTEGER).
    # If found, drop all our tables and let create_all rebuild from scratch.
    try:
        existing_tables = set(inspect(engine).get_table_names())
        if "users" in existing_tables:
            with engine.begin() as conn:
                cols = conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()
                # Each row: (cid, name, type, notnull, dflt_value, pk)
                pk_col = next((c for c in cols if c[5] == 1), None)
                if pk_col and "INT" in (pk_col[2] or "").upper():
                    # Old schema — drop all tables in dependency order
                    for tbl in (
                        "job_analysis_cache", "match_report_cache",
                        "job_run_jobs", "job_runs", "job_postings",
                        "cv_documents", "job_vacancies", "users_cv", "users",
                    ):
                        conn.exec_driver_sql(f"DROP TABLE IF EXISTS [{tbl}]")
    except Exception:
        pass

    # ── Lightweight column migrations (for UUID-schema DBs) ───────────────────
    try:
        existing_tables = set(inspect(engine).get_table_names())

        if "users_cv" in existing_tables:
            with engine.begin() as conn:
                cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(users_cv)").fetchall()]
                if "all_text" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users_cv ADD COLUMN all_text TEXT")
                conn.exec_driver_sql("UPDATE users_cv SET all_text = '' WHERE all_text IS NULL")
                if "years_experience" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users_cv ADD COLUMN years_experience REAL")
                if "experience_bucket" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users_cv ADD COLUMN experience_bucket TEXT")
                if "cv_hash" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users_cv ADD COLUMN cv_hash TEXT")
                if "last_used_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users_cv ADD COLUMN last_used_at DATETIME")

        if "cv_documents" in existing_tables:
            with engine.begin() as conn:
                cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(cv_documents)").fetchall()]
                if "content_hash" not in cols:
                    conn.exec_driver_sql("ALTER TABLE cv_documents ADD COLUMN content_hash TEXT")
    except Exception:
        pass

    Base.metadata.create_all(engine)

    # Ensure the guest user (fixed UUID) always exists.
    try:
        with Session() as session:
            exists = session.query(User).filter_by(id=GUEST_USER_UUID).first()
            if not exists:
                session.add(
                    User(
                        id=GUEST_USER_UUID,
                        email="guest@local",
                        password_salt=None,
                        password_hash=None,
                        api_token=None,
                    )
                )
                session.commit()
    except Exception:
        pass
    print(f"Database ready at: {DB_PATH}")


def seed_cv() -> None:
    """Insert Ivan's CV as the first record (skips if already present)."""
    session = Session()
    try:
        if session.query(UsersCv).first():
            print("CV record already exists — skipping seed.")
            return

        # Keep a full-text representation in all_text as well.
        all_text = "\n".join(
            [
                "Python Developer (Entry Level)",
                "Ivan Petrenko",
                "ivan.petrenko.dev@example.com",
                "+380 (XX) XXX-XX-XX",
                "Lviv, Ukraine (open to worldwide relocation)",
                "https://github.com/ivanpetrenko",
                "https://linkedin.com/in/ivanpetrenko",
                "",
                "Entry-level Python Developer with a solid understanding of backend development fundamentals, OOP, and REST API design.",
                "Skills: Python, Flask, Django, REST, SQL",
                "Tools: Git, Docker, Postman, Linux",
                "",
                "Projects:",
                "1. Task Manager API — Flask + SQLite",
                "2. Weather Application — Python + requests",
                "3. Simple Blog Platform — Django",
                "",
                "Education: Lviv Polytechnic National University, Information Systems / Software Engineering, 2022 – Present",
            ]
        ).strip()

        cv = UsersCv(
            job_title          = "Python Developer (Entry Level)",
            full_name          = "Ivan Petrenko",
            email              = "ivan.petrenko.dev@example.com",
            phone              = "+380 (XX) XXX-XX-XX",
            location           = "Lviv, Ukraine (open to worldwide relocation)",
            github_url         = "https://github.com/ivanpetrenko",
            linkedin_url       = "https://linkedin.com/in/ivanpetrenko",
            all_text           = all_text,
            profile_summary    = (
                "Entry-level Python Developer with a solid understanding of backend "
                "development fundamentals, OOP, and REST API design. Passionate about "
                "building clean and efficient code, learning new technologies, and "
                "contributing to real-world projects."
            ),
            programming_skills = (
                "Python (OOP, modules, error handling, basic design patterns), "
                "Flask, Django (basic backend development), "
                "REST API development and integration, "
                "SQL (PostgreSQL, MySQL — basic queries and schema design)"
            ),
            tools_and_tech     = (
                "Git / GitHub (version control), Docker (basic), "
                "Postman (API testing), Linux (basic CLI), VS Code / PyCharm"
            ),
            other_skills       = (
                "HTML / CSS (basic), Data Structures & Algorithms (fundamentals), "
                "Agile / Scrum basics, English B1–B2"
            ),
            projects           = (
                "1. Task Manager API — Flask + SQLite, REST API with JWT auth, "
                "filtering and status tracking.\n"
                "2. Weather Application — Python + requests, public weather API, CLI output.\n"
                "3. Simple Blog Platform — Django backend, admin panel, basic DB integration."
            ),
            education          = (
                "Lviv Polytechnic National University, "
                "Information Systems / Software Engineering, 2022 – Present"
            ),
            career_objective   = (
                "To obtain a Junior Python Developer position where I can grow "
                "professionally, contribute to real-world backend systems, and improve "
                "my software engineering skills in a collaborative environment."
            ),
            additional_info    = (
                "Open to worldwide relocation. Fast learner with strong self-study "
                "discipline. Experience in team-based university projects."
            ),
        )
        session.add(cv)
        session.commit()
        print("CV record seeded successfully.")
    finally:
        session.close()


# ── Run directly to initialise ────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    seed_cv()


# Backwards-compatible alias (older code used MyCv / my_cv)
MyCv = UsersCv

