from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JobDescriptionExtension:
    job_title: str
    source_url: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobDescriptionExtension":
        return cls(
            job_title=str(data["job_title"]),
            source_url=str(data["source_url"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_title": self.job_title,
            "source_url": self.source_url,
        }


@dataclass(frozen=True, slots=True)
class JobDescriptionList:
    jobs: list[JobDescriptionExtension]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> "JobDescriptionList":
        return cls(jobs=[JobDescriptionExtension.from_dict(item) for item in data])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobDescriptionList":
        if "jobs" not in data:
            raise ValueError("Expected a dict with 'jobs' key")
        return cls.from_list(data["jobs"])

    @classmethod
    def from_json(cls, data: str) -> "JobDescriptionList":
        parsed = json.loads(data)
        if isinstance(parsed, dict) and "jobs" in parsed:
            return cls.from_dict(parsed)
        if isinstance(parsed, list):
            return cls.from_list(parsed)
        raise ValueError("Expected a JSON object with 'jobs' key or a JSON array")

    def to_list(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.jobs]

    def to_dict(self) -> dict[str, Any]:
        return {"jobs": self.to_list()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
