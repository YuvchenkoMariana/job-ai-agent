"""
enricher.py — fetches a job vacancy page and uses OpenAI to fill in all null fields.

Usage:
    from backend.ai.enricher import enrich_job
    data = enrich_job(source_url="https://jobs.dou.ua/...", job_title="Python Dev")
    # data is a dict with keys: company_name, location, role_summary, ...
"""
from __future__ import annotations

import json
import os

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

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


# ── Page fetcher ──────────────────────────────────────────────────────────────
def _fetch_text(url: str, max_chars: int = 8_000) -> str:
    """Download a job page and return clean plain text (max_chars limit)."""
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

    text = soup.get_text(separator="\n", strip=True)
    return text[:max_chars]


# ── Main enricher ─────────────────────────────────────────────────────────────
def enrich_job(source_url: str, job_title: str) -> dict:
    """
    Fetch the job page at source_url, ask OpenAI to extract structured fields,
    and return a dict ready to be merged into a JobVacancy row.
    """
    text = _fetch_text(source_url)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": _PROMPT.format(job_title=job_title, text=text),
            }
        ],
    )

    return json.loads(response.choices[0].message.content)

