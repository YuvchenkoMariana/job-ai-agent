"""
database.py — SQLAlchemy models for Jobs Search project.

Tables
──────
  my_cv         → stores YOUR CV split into semantic blocks
  job_vacancies → stores scraped / pasted job listings split into blocks
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os

SF_TZ = ZoneInfo("America/Los_Angeles")

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


# ── Table 1: my_cv ────────────────────────────────────────────────────────────
class MyCv(Base):
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
    __tablename__ = "my_cv"

    id                  = Column(Integer, primary_key=True, autoincrement=True)

    # ── Position ──────────────────────────────────────────────────────────────
    job_title           = Column(String(200), nullable=False)          # e.g. "Python Developer (Entry Level)"
    # todo delete limit from str, make all filead unlimetless
    # ── Contact ───────────────────────────────────────────────────────────────
    full_name           = Column(String(200),  nullable=True)
    email               = Column(String(200),  nullable=True)
    phone               = Column(String(50),   nullable=True)
    location            = Column(String(300),  nullable=True)
    github_url          = Column(String(300),  nullable=True)
    linkedin_url        = Column(String(300),  nullable=True)

    # ── Content blocks ────────────────────────────────────────────────────────
    profile_summary     = Column(Text, nullable=True)                   # "About me" paragraph
    programming_skills  = Column(Text, nullable=True)                   # Python, Flask, Django, REST…
    tools_and_tech      = Column(Text, nullable=True)                   # Git, Docker, Postman, Linux…
    other_skills        = Column(Text, nullable=True)                   # English B2, Agile, DSA…
    projects            = Column(Text, nullable=True)                   # list of projects + descriptions
    education           = Column(Text, nullable=True)                   # university, field, years
    career_objective    = Column(Text, nullable=True)                   # what role you want
    additional_info     = Column(Text, nullable=True)                   # relocation, misc notes

    # ── Meta ──────────────────────────────────────────────────────────────────
    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<MyCv id={self.id} job_title='{self.job_title}' name='{self.full_name}'>"


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

    id                  = Column(Integer, primary_key=True, autoincrement=True)

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

    # ── Meta ──────────────────────────────────────────────────────────────────
    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<JobVacancy id={self.id} title='{self.job_title}' company='{self.company_name}'>"


# ── In-memory CV store (no DB required) ──────────────────────────────────────
class MemoryCV:
    """
    Stores one or more CV records in plain Python dicts — no database needed.

    Usage:
        store = MemoryCV()
        store.add(job_title="Python Developer", full_name="Ivan", ...)
        store.add(job_title="Backend Engineer",  full_name="Ivan", ...)

        store.all()           → list of all CV dicts
        store.get(1)          → single CV dict by id
        store.update(1, email="new@mail.com")
        store.delete(1)
        store.clear()
        print(store)          → summary of all records
    """

    # shared fields — mirrors MyCv columns (excluding id / timestamps)
    FIELDS: list[str] = [
        "job_title", "full_name", "email", "phone", "location",
        "github_url", "linkedin_url", "profile_summary",
        "programming_skills", "tools_and_tech", "other_skills",
        "projects", "education", "career_objective", "additional_info",
    ]

    def __init__(self) -> None:
        self._records: list[dict] = []
        self._next_id: int = 1

    # ── write ──────────────────────────────────────────────────────────────
    def add(self, **kwargs) -> dict:
        """Create a new CV record and return it."""
        record: dict = {"id": self._next_id}
        for field in self.FIELDS:
            record[field] = kwargs.get(field)           # None if not provided
        record["created_at"] = datetime.now(timezone.utc)
        record["updated_at"] = datetime.now(timezone.utc)
        self._records.append(record)
        self._next_id += 1
        return record

    def update(self, record_id: int, **kwargs) -> dict:
        """Update fields of an existing record by id. Returns updated record."""
        record = self.get(record_id)
        for key, value in kwargs.items():
            if key in self.FIELDS:
                record[key] = value
        record["updated_at"] = datetime.now(timezone.utc)
        return record

    def delete(self, record_id: int) -> None:
        """Remove a record by id."""
        self._records = [r for r in self._records if r["id"] != record_id]

    def clear(self) -> None:
        """Remove all records and reset the id counter."""
        self._records = []
        self._next_id = 1

    # ── read ───────────────────────────────────────────────────────────────
    def all(self) -> list[dict]:
        """Return a copy of all records."""
        return list(self._records)

    def get(self, record_id: int) -> dict:
        """Return a single record by id. Raises KeyError if not found."""
        for record in self._records:
            if record["id"] == record_id:
                return record
        raise KeyError(f"MemoryCV: no record with id={record_id}")

    def __len__(self) -> int:
        return len(self._records)

    def __repr__(self) -> str:
        lines = [f"MemoryCV ({len(self._records)} record(s)):"]
        for r in self._records:
            lines.append(
                f"  id={r['id']}  job_title='{r['job_title']}'  name='{r['full_name']}'"
            )
        return "\n".join(lines)


# ── Init helpers ──────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables (safe to call multiple times — skips existing)."""
    Base.metadata.create_all(engine)
    print(f"Database ready at: {DB_PATH}")


def seed_cv() -> None:
    """Insert Ivan's CV as the first record (skips if already present)."""
    session = Session()
    try:
        if session.query(MyCv).first():
            print("CV record already exists — skipping seed.")
            return

        cv = MyCv(
            job_title          = "Python Developer (Entry Level)",
            full_name          = "Ivan Petrenko",
            email              = "ivan.petrenko.dev@example.com",
            phone              = "+380 (XX) XXX-XX-XX",
            location           = "Lviv, Ukraine (open to worldwide relocation)",
            github_url         = "https://github.com/ivanpetrenko",
            linkedin_url       = "https://linkedin.com/in/ivanpetrenko",
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

