"""CV classifier: detect a DOU vacancies category from an uploaded CV.

Goal
----
Given raw CV text, determine which DOU category page should be used for job
searching, e.g.:
- Python -> https://jobs.dou.ua/vacancies/?category=Python
- PHP -> https://jobs.dou.ua/vacancies/?category=PHP
- Project Manager -> https://jobs.dou.ua/vacancies/?category=Project%20Manager
- Product Manager -> https://jobs.dou.ua/vacancies/?category=Product%20Manager

The API uses a heuristic classifier by default (fast, no network).
If OPENAI_API_KEY is set, it can optionally ask OpenAI for a more robust
classification.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


DouCategory = Literal["Python", "PHP", "Project Manager", "Product Manager"]


@dataclass(frozen=True, slots=True)
class CvClassification:
    category: DouCategory
    job_title: str | None
    confidence: float
    method: str  # "heuristic" | "openai"


_ALLOWED: list[DouCategory] = [
    "Python",
    "PHP",
    "Project Manager",
    "Product Manager",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def classify_cv_heuristic(cv_text: str) -> CvClassification:
    """Fast local classifier based on keywords."""
    t = _normalize(cv_text)

    # Prioritize explicit manager roles.
    if "project manager" in t or "pm (project" in t or "project-management" in t:
        return CvClassification(category="Project Manager", job_title="Project Manager", confidence=0.92, method="heuristic")

    if "product manager" in t or "product-management" in t:
        return CvClassification(category="Product Manager", job_title="Product Manager", confidence=0.92, method="heuristic")

    # Then languages.
    if re.search(r"\bphp\b", t):
        return CvClassification(category="PHP", job_title="PHP Developer", confidence=0.9, method="heuristic")

    if re.search(r"\bpython\b", t):
        return CvClassification(category="Python", job_title="Python Developer", confidence=0.9, method="heuristic")

    # Fallback
    return CvClassification(category="Python", job_title=None, confidence=0.2, method="heuristic")


def _openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def classify_cv(cv_text: str) -> CvClassification:
    """Classify CV using heuristics and (optionally) OpenAI.

    Strategy:
    - Use heuristics first.
    - If heuristics confidence is low AND OPENAI_API_KEY is configured, ask OpenAI.

    This keeps the app working offline and keeps tests deterministic.
    """

    h = classify_cv_heuristic(cv_text)
    if h.confidence >= 0.85:
        return h

    if not _openai_available():
        return h

    # Only call OpenAI when explicitly allowed (opt-in), to avoid surprising costs.
    if os.getenv("OPENAI_CV_CLASSIFIER", "0") != "1":
        return h

    try:
        from openai import OpenAI
        import json

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "You are a CV role classifier. Read the CV text and decide which DOU category "
            "page should be used for searching vacancies.\n\n"
            f"Allowed categories: {', '.join(_ALLOWED)}.\n\n"
            "Return ONLY a valid JSON object with keys:\n"
            "{\n"
            "  \"category\": one of the allowed categories,\n"
            "  \"job_title\": a short role title (e.g. 'PHP Developer'),\n"
            "  \"confidence\": a number from 0 to 1\n"
            "}\n\n"
            "CV text:\n"
            + cv_text[:8000]
        )

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_CV_MODEL", "gpt-4o-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.choices[0].message.content)

        category = str(data.get("category") or "Python")
        if category not in _ALLOWED:
            category = "Python"

        job_title = data.get("job_title")
        confidence = float(data.get("confidence") or 0.5)

        return CvClassification(
            category=category,  # type: ignore[arg-type]
            job_title=str(job_title) if job_title else None,
            confidence=max(0.0, min(1.0, confidence)),
            method="openai",
        )
    except Exception:
        # If OpenAI fails for any reason, fall back.
        return h

