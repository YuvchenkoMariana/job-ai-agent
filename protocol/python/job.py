from __future__ import annotations

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
