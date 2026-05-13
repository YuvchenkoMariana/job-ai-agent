"""Parse a raw CV text into the structured `users_cv` shape.

We support two modes:
- Heuristic parsing (offline fallback): extracts a minimal subset (job_title, email, links, experience bucket).
- OpenAI parsing (preferred when available): if OPENAI_API_KEY is set and
  OPENAI_CV_PARSER is not "0", we ask the model to return a JSON object matching
  the `UsersCv` fields.

Why there is a heuristic fallback:
- tests should run without network
- the app should still work when OpenAI is unavailable
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class ParsedCv:
    job_title: str
    all_text: str
    years_experience: float | None = None
    # One of: 0-1, 1-3, 3-5, 5plus (DOU-compatible)
    experience_bucket: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    profile_summary: str | None = None
    programming_skills: str | None = None
    tools_and_tech: str | None = None
    other_skills: str | None = None
    projects: str | None = None
    education: str | None = None
    career_objective: str | None = None
    additional_info: str | None = None

    def to_sa_kwargs(self) -> dict:
        return {
            "job_title": self.job_title,
            "all_text": self.all_text,
            "years_experience": self.years_experience,
            "experience_bucket": self.experience_bucket,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "github_url": self.github_url,
            "linkedin_url": self.linkedin_url,
            "profile_summary": self.profile_summary,
            "programming_skills": self.programming_skills,
            "tools_and_tech": self.tools_and_tech,
            "other_skills": self.other_skills,
            "projects": self.projects,
            "education": self.education,
            "career_objective": self.career_objective,
            "additional_info": self.additional_info,
        }


_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)


def _bucket_from_years(years: float | None) -> str | None:
    if years is None:
        return None
    if years < 1:
        return "0-1"
    if years < 3:
        return "1-3"
    if years < 5:
        return "3-5"
    return "5plus"


def _extract_years_experience(text: str) -> float | None:
    """Best-effort heuristic extraction of years of experience.

    We intentionally keep this conservative:
    - Only numbers near 'years/yrs' or Ukrainian 'років/роки/р.' or 'місяців'
    - Reject unrealistically large values to avoid matching years like 2024.
    """

    t = text.lower()

    # If the CV explicitly signals junior/entry-level, treat as < 1 year.
    # This covers many CVs that do not mention a numeric years-of-experience.
    if re.search(r"\bentry\s*[- ]\s*level\b", t) or re.search(r"\bjunior\b", t) or re.search(r"\btrainee\b", t) or re.search(r"\bintern\b", t):
        return 0.5

    # Common phrases for < 1 year
    if re.search(r"\bless\s+than\s+1\s+year\b", t) or re.search(r"менше\s+року", t):
        return 0.5

    candidates: list[float] = []

    # Ranges like 1-3 years
    for m in re.finditer(
        r"\b(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?|роки|років|р\.)\b",
        t,
    ):
        a = float(m.group(1))
        b = float(m.group(2))
        candidates.append(max(a, b))

    # Plus like 5+ years
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?|роки|років|р\.)\b", t):
        candidates.append(float(m.group(1)))

    # Simple like 2 years
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?|роки|років|р\.)\b", t):
        candidates.append(float(m.group(1)))

    # Months like 6 months
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:months?|mos?|місяц(?:ів|і|я)?)\b", t):
        candidates.append(float(m.group(1)) / 12.0)

    # Filter unrealistic values (avoid matching 2024 etc)
    candidates = [c for c in candidates if 0 <= c <= 50]
    if not candidates:
        return None

    return max(candidates)


def _guess_job_title(text: str) -> str:
    t = text.lower()

    # explicit manager roles first
    if "product manager" in t:
        return "Product Manager"
    if "project manager" in t:
        return "Project Manager"

    # languages
    if re.search(r"\bphp\b", t):
        return "PHP Developer"
    if re.search(r"\bpython\b", t):
        return "Python Developer"

    # fallback required by schema
    return "Software Developer"


def parse_cv_heuristic(cv_text: str) -> ParsedCv:
    job_title = _guess_job_title(cv_text)

    years = _extract_years_experience(cv_text)
    bucket = _bucket_from_years(years)

    email = None
    m = _EMAIL_RE.search(cv_text)
    if m:
        email = m.group(0)

    github_url = None
    linkedin_url = None
    for u in _URL_RE.findall(cv_text):
        if "github.com" in u.lower() and github_url is None:
            github_url = u.rstrip(")].,;")
        if "linkedin.com" in u.lower() and linkedin_url is None:
            linkedin_url = u.rstrip(")].,;")

    # naive full name heuristic: first non-empty short line that isn't a header
    full_name = None
    for line in (l.strip() for l in cv_text.splitlines()):
        if not line:
            continue
        if len(line) > 60:
            continue
        if any(k in line.lower() for k in ["cv", "resume", "contact", "skills", "education", "projects"]):
            continue
        # looks like name if has 2 words and no punctuation
        if re.match(r"^[A-Za-zА-Яа-яЇїІіЄєҐґ'`\-]+\s+[A-Za-zА-Яа-яЇїІіЄєҐґ'`\-]+$", line):
            full_name = line
            break

    return ParsedCv(
        job_title=job_title,
        all_text=cv_text,
        years_experience=years,
        experience_bucket=bucket,
        full_name=full_name,
        email=email,
        github_url=github_url,
        linkedin_url=linkedin_url,
    )


def _openai_available() -> bool:
    # Default: ON when OPENAI_API_KEY is present.
    # Disable explicitly with: OPENAI_CV_PARSER=0
    return bool(os.getenv("OPENAI_API_KEY")) and os.getenv("OPENAI_CV_PARSER", "1") != "0"


def parse_cv(cv_text: str) -> ParsedCv:
    """Parse CV into structured fields.

    Uses OpenAI only when explicitly enabled.
    """
    heuristic = parse_cv_heuristic(cv_text)

    if not _openai_available():
        return heuristic

    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "You are a CV parser. Extract structured fields from the CV text.\n\n"
            "Return ONLY a valid JSON object with exactly these keys (use null if missing):\n"
            "{\n"
            '  "job_title": "string",\n'
            '  "years_experience": "number or null",\n'
            '  "full_name": "string or null",\n'
            '  "email": "string or null",\n'
            '  "phone": "string or null",\n'
            '  "location": "string or null",\n'
            '  "github_url": "string or null",\n'
            '  "linkedin_url": "string or null",\n'
            '  "profile_summary": "string or null",\n'
            '  "programming_skills": "string or null",\n'
            '  "tools_and_tech": "string or null",\n'
            '  "other_skills": "string or null",\n'
            '  "projects": "string or null",\n'
            '  "education": "string or null",\n'
            '  "career_objective": "string or null",\n'
            '  "additional_info": "string or null"\n'
            "}\n\n"
            "CV text:\n"
            + cv_text[:12000]
        )

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_CV_MODEL", "gpt-4o-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.choices[0].message.content)

        job_title = str(data.get("job_title") or heuristic.job_title).strip() or heuristic.job_title

        years_experience = data.get("years_experience")
        try:
            years_experience_f = float(years_experience) if years_experience is not None else None
        except Exception:
            years_experience_f = heuristic.years_experience

        bucket = _bucket_from_years(years_experience_f)

        return ParsedCv(
            job_title=job_title,
            all_text=cv_text,
            years_experience=years_experience_f,
            experience_bucket=bucket,
            full_name=data.get("full_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            location=data.get("location"),
            github_url=data.get("github_url"),
            linkedin_url=data.get("linkedin_url"),
            profile_summary=data.get("profile_summary"),
            programming_skills=data.get("programming_skills"),
            tools_and_tech=data.get("tools_and_tech"),
            other_skills=data.get("other_skills"),
            projects=data.get("projects"),
            education=data.get("education"),
            career_objective=data.get("career_objective"),
            additional_info=data.get("additional_info"),
        )
    except Exception:
        return heuristic

