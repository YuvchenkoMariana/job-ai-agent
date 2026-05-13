"""
enricher.py — 3-step pipeline for enriching job vacancies.

Step 1  /api/jobs/sync
        Plugin sends {job_title, source_url} → saved to DB as a stub record.
        (handled by fast_api.py — no function needed here)

Step 2  fetch_and_save_text(job_id)
        Reads source_url from DB → downloads the page → saves full raw text
        into the full_text column.

Step 3  enrich_from_text(job_id)
        Reads full_text from DB → sends to OpenAI → parses structured fields
        → saves company_name, location, salary, etc. back to DB.
"""
from __future__ import annotations

import json
import os

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

from backend.db.database import Session, JobPosting

load_dotenv()

# ── Prompt ────────────────────────────────────────────────────────────────────
_PROMPT = """\
You are a job description parser. Read the job posting below and extract structured data.

Return ONLY a valid JSON object with exactly these keys (use null for any field not mentioned):

{{
  "company_name":           "string or null",
  "company_overview":       "string or null",
  "location":               "string or null",
  "work_type":              "Full-time | Part-time | Contract | Remote | Hybrid | null",
  "role_summary":           "1-3 sentence summary of the role, or null",
  "responsibilities":       "bullet list of duties as a single string, or null",
  "required_quals":         "must-have skills / experience as a single string, or null",
  "preferred_quals":        "nice-to-have skills as a single string, or null",
  "tools_and_methods":      "tech stack / tools as a single string, or null",
  "what_success_looks":     "KPIs / outcomes as a single string, or null",
  "salary_min":             integer or null,
  "salary_max":             integer or null,
  "salary_currency":        "USD | UAH | EUR | null",
  "language_requirements":  "e.g. English B2, Ukrainian Native — or null"
}}

Job title: {job_title}

Job posting text:
{text}
"""

_ENRICH_FIELDS = {
    "company_name", "company_overview", "location", "work_type",
    "role_summary", "responsibilities", "required_quals", "preferred_quals",
    "tools_and_methods", "what_success_looks",
    "salary_min", "salary_max", "salary_currency", "language_requirements",
}


# ── Step 2 ────────────────────────────────────────────────────────────────────
def fetch_and_save_text(job_id: str, *, user_id: str | None = None, force: bool = False) -> str:
    """
    Step 2: Fetch the job page from source_url and save the raw text
    into the full_text column in the DB.

    Returns the saved text.
    """
    with Session() as session:
        # JobPosting is global (stored once). `user_id` is accepted for backward
        # compatibility but intentionally not used for filtering.
        job = session.query(JobPosting).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if not job.source_url:
            raise ValueError(f"Job {job_id} has no source_url")

        # Cache: do not re-fetch the same vacancy page unless forced.
        if job.full_text and not force:
            return str(job.full_text)

        text = _fetch_text(job.source_url)
        job.full_text = text
        session.commit()

    return text


# ── Step 3 ────────────────────────────────────────────────────────────────────
def enrich_from_text(job_id: str, *, user_id: str | None = None) -> dict:
    """
    Step 3: Read full_text from the DB, send to OpenAI, parse structured fields,
    and save them back to the DB.

    Returns the enriched fields dict.
    """
    with Session() as session:
        job = session.query(JobPosting).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if not job.full_text:
            raise ValueError(f"Job {job_id} has no full_text — run step 2 first")

        # Cache: if already enriched, do nothing (prevents spending OpenAI tokens twice).
        if job.role_summary:
            return {"role_summary": job.role_summary}

        enriched = _call_openai(job_title=job.job_title, text=job.full_text)

        for field, value in enriched.items():
            if field in _ENRICH_FIELDS and value is not None:
                setattr(job, field, value)
        session.commit()

    return enriched


# ── Internal helpers ──────────────────────────────────────────────────────────
def _fetch_text(url: str, max_chars: int = 8_000) -> str:
    """Download a job page and return clean plain text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    return soup.get_text(separator="\n", strip=True)[:max_chars]


def _call_openai(job_title: str, text: str) -> dict:
    """Send text to OpenAI and return parsed structured fields."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": _PROMPT.format(job_title=job_title, text=text),
        }],
    )
    return json.loads(response.choices[0].message.content)


# ── Run all 3 steps manually ──────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint
    from backend.db.database import init_db

    init_db()

    # ── Step 1: save stub (simulate what /api/jobs/sync does) ─────────────────
    with Session() as session:
        existing = session.query(JobPosting).filter_by(
            source_url="https://jobs.dou.ua/companies/skelar/vacancies/355543/?from=list_hot"
        ).first()
        if not existing:
            job = JobPosting(
                job_title="Backend Engineer (PHP) — TENTENS Tech",
                source_url="https://jobs.dou.ua/companies/skelar/vacancies/355543/?from=list_hot",
            )
            session.add(job)
            session.commit()
            job_id = job.id
            print(f"Step 1 ✅ saved stub  id={job_id}")
        else:
            job_id = existing.id
            print(f"Step 1 ✅ already exists  id={job_id}")

    # ── Step 2: fetch page text → DB ──────────────────────────────────────────
    text = fetch_and_save_text(job_id)
    print(f"Step 2 ✅ saved {len(text)} chars of full_text")

    # ── Step 3: OpenAI reads full_text → fills fields in DB ───────────────────
    result = enrich_from_text(job_id)
    print("Step 3 ✅ enriched fields:")
    pprint.pprint(result)

