from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.db.database import JobVacancy


@dataclass(frozen=True, slots=True)
class JobDescription:
    # ── Required (plugin always provides these) ───────────────────────────────
    job_title: str
    source_url: str

    # ── Set by DB on insert ───────────────────────────────────────────────────
    id: int | None = None

    # ── Enriched later (AI / manual) ─────────────────────────────────────────
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

    # ── Constructors ──────────────────────────────────────────────────────────

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
    def from_row(cls, row: "JobVacancy") -> "JobDescription":
        """Convert a SQLAlchemy JobVacancy row into a JobDescription."""
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


@dataclass(frozen=True, slots=True)
class JobDescriptionList:
    jobs: list[JobDescription]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> "JobDescriptionList":
        return cls(jobs=[JobDescription.from_dict(item) for item in data])

    @classmethod
    def from_json(cls, data: str) -> "JobDescriptionList":
        parsed = json.loads(data)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array of job descriptions")
        return cls.from_list(parsed)

    def to_list(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.jobs]

    def to_json(self) -> str:
        return json.dumps(self.to_list(), ensure_ascii=False)
