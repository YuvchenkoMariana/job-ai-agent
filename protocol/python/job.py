from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JobDescription:
    id: int
    title: str
    href: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobDescription":
        return cls(
            id=int(data["id"]),
            title=str(data["title"]),
            href=str(data["href"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "href": self.href}


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

