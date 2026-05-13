"""CV ↔ Job matching (match score + optional OpenAI report).

This module provides:
- a deterministic heuristic scorer (offline)
- an optional OpenAI-based narrative report (opt-in)

Why heuristic exists:
- UI should work even without OpenAI
- tests must run offline

OpenAI is only used when:
- OPENAI_API_KEY is set
- OPENAI_MATCHER=1

The matcher is intentionally simple: it relies on token overlap between
candidate CV text and job text (title + any available fields).
"""

from __future__ import annotations

import math
import os
import re
import html
from dataclasses import dataclass
from typing import Any, Iterable

from dotenv import load_dotenv

from backend.ai.cv_classifier import classify_cv

load_dotenv()


_SKILL_PATTERNS: list[tuple[str, list[str]]] = [
    ("Python", [r"\bpython\b"]),
    ("Flask", [r"\bflask\b"]),
    ("Django", [r"\bdjango\b"]),
    ("FastAPI", [r"\bfastapi\b"]),
    ("REST API", [r"\brest\b", r"\bapi\b", r"rest\s*api"]),
    ("SQL", [r"\bsql\b", r"\bpostgres", r"\bmysql\b", r"\bsqlite\b"]),
    ("PostgreSQL", [r"postgres", r"postgresql"]),
    ("MySQL", [r"\bmysql\b"]),
    ("SQLite", [r"\bsqlite\b"]),
    ("SQLAlchemy", [r"sqlalchemy"]),
    ("Docker", [r"\bdocker\b"]),
    ("Linux", [r"\blinux\b"]),
    ("Git", [r"\bgit\b", r"github"]),
    ("Selenium", [r"\bselenium\b"]),
    ("BeautifulSoup", [r"beautifulsoup", r"\bbs4\b"]),
    ("Scrapy", [r"\bscrapy\b"]),
    ("Pandas", [r"\bpandas\b"]),
    ("NumPy", [r"\bnumpy\b"]),
    ("Machine Learning", [r"machine\s*learning", r"\bml\b"]),
    ("LLMs / GenAI", [r"\bllm\b", r"genai", r"openai", r"gpt\b"]),
    ("AWS", [r"\baws\b", r"amazon\s+web\s+services"]),
    ("Azure", [r"\bazure\b"]),
]


def _text_has_any(text_l: str, patterns: list[str]) -> bool:
    return any(re.search(p, text_l, re.I) for p in patterns)


def _extract_years_requirement(text: str) -> float | None:
    """Extract a rough 'years of experience required' number from job text."""

    t = text.lower()
    # Examples: "1+ years", "2 years", "3+ yrs"
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", t)
    if not m:
        # Ukrainian/Russian variants
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:роки|років|р\.)\b", t)
    if not m:
        return None
    try:
        v = float(m.group(1))
        if 0 <= v <= 50:
            return v
    except Exception:
        return None
    return None


def _cv_years_estimate(cv: Any) -> float | None:
    y = getattr(cv, "years_experience", None)
    if isinstance(y, (int, float)):
        return float(y)
    b = getattr(cv, "experience_bucket", None)
    if b == "0-1":
        return 0.5
    if b == "1-3":
        return 2.0
    if b == "3-5":
        return 4.0
    if b == "5plus":
        return 6.0
    return None


def _build_requirements_table(cv: Any, job: Any) -> tuple[list[dict[str, str]], list[str]]:
    """Create a requirements table similar to backend/data/cv_job_analysis.md.

    Returns:
        (rows, gaps)
    """

    cv_text_l = _cv_text(cv).lower()
    job_text_l = _job_text(job).lower()

    rows: list[dict[str, str]] = []
    gaps: list[str] = []

    for label, patterns in _SKILL_PATTERNS:
        if not _text_has_any(job_text_l, patterns):
            continue
        has_cv = _text_has_any(cv_text_l, patterns)
        status = "✅" if has_cv else "❌"
        evidence = "mentioned in CV" if has_cv else "not found in CV"
        rows.append({"requirement": label, "status": status, "evidence": evidence})
        if not has_cv:
            gaps.append(label)

    # Experience requirement row
    yrs_req = _extract_years_requirement(job_text_l)
    if yrs_req is not None:
        cv_yrs = _cv_years_estimate(cv)
        ok = cv_yrs is not None and cv_yrs >= yrs_req
        status = "✅" if ok else "❌"
        evidence = f"job asks ~{yrs_req:g}+ years; CV has ~{cv_yrs:g} years" if cv_yrs is not None else f"job asks ~{yrs_req:g}+ years; CV years unknown"
        rows.insert(0, {"requirement": "Experience (years)", "status": status, "evidence": evidence})
        if not ok:
            gaps.insert(0, f"Experience >= {yrs_req:g} year(s)")

    if not rows:
        rows.append({"requirement": "(Not enough job text to extract requirements)", "status": "—", "evidence": "Run enrichment to fetch full_text for better analysis."})

    return rows, gaps


def _render_table_html(rows: list[dict[str, str]]) -> str:
    th = "<thead><tr><th>Requirement</th><th>CV match</th><th>Evidence</th></tr></thead>"
    tds = []
    for r in rows:
        tds.append(
            "<tr>"
            f"<td>{html.escape(r.get('requirement',''))}</td>"
            f"<td class='analysis-status'>{html.escape(r.get('status',''))}</td>"
            f"<td>{html.escape(r.get('evidence',''))}</td>"
            "</tr>"
        )
    body = "<tbody>" + "".join(tds) + "</tbody>"
    return f"<table class='analysis-table'>{th}{body}</table>"


def _render_job_analysis_html(cv: Any, job: Any, item: MatchItem) -> dict[str, Any]:
    rows, gaps = _build_requirements_table(cv, job)

    strengths = [r["requirement"] for r in rows if r.get("status") == "✅" and r.get("requirement")]
    recs: list[str] = []
    for g in gaps[:8]:
        # Simple mapping to recommendations
        recs.append(f"Improve / add evidence for: {g}")
    if not recs:
        recs = ["Tailor your CV bullets to mirror this vacancy keywords (truthfully)."]

    title = html.escape(getattr(job, "job_title", "") or "")
    url = html.escape(getattr(job, "source_url", "") or "")

    why_line = ""
    if strengths:
        why_line = "<p><b>Where you match:</b> " + html.escape(", ".join(strengths[:12])) + "</p>"

    gaps_html = "<ul>" + "".join(f"<li>{html.escape(g)}</li>" for g in gaps[:10]) + "</ul>" if gaps else "<div class='muted'>No major gaps detected from available text.</div>"
    recs_html = "<ul>" + "".join(f"<li>{html.escape(r)}</li>" for r in recs[:10]) + "</ul>"

    table_html = _render_table_html(rows)

    html_out = (
        f"<div class='analysis-head'><div class='analysis-title'>{title}</div>"
        f"<div class='analysis-meta'>Score: {item.score:.0%} • Method: heuristic</div>"
        + (f"<div class='analysis-url'><a href='{url}' target='_blank' rel='noreferrer'>{url}</a></div>" if url else "")
        + "</div>"
        + "<h4>Requirements vs CV</h4>"
        + table_html
        + why_line
        + "<h4>Gaps</h4>" + gaps_html
        + "<h4>Recommendations</h4>" + recs_html
    )

    # Also provide markdown (handy for copy/paste)
    md_lines = [
        f"### {getattr(job, 'job_title', '')}\n",
        f"Score: {item.score:.0%} (heuristic)\n",
    ]
    if getattr(job, "source_url", None):
        md_lines.append(f"URL: {getattr(job, 'source_url')}\n")
    md_lines.append("\n| Requirement | CV match | Evidence |\n|---|---|---|")
    for r in rows:
        md_lines.append(f"| {r.get('requirement','')} | {r.get('status','')} | {r.get('evidence','')} |")
    if gaps:
        md_lines.append("\n**Gaps:**\n" + "\n".join(f"- {g}" for g in gaps[:10]))
    md_lines.append("\n**Recommendations:**\n" + "\n".join(f"- {x}" for x in recs[:10]))

    return {
        "breakdown": {"rows": rows, "gaps": gaps, "recommendations": recs},
        "html": html_out,
        "markdown": "\n".join(md_lines).strip(),
    }


_STOPWORDS = {
    # English
    "a", "an", "and", "or", "the", "to", "of", "in", "for", "with", "on", "at", "by", "as",
    "from", "this", "that", "these", "those", "is", "are", "was", "were", "be", "been", "being",
    "will", "would", "can", "could", "should", "may", "might", "must", "we", "you", "they", "i",
    "our", "your", "their", "my", "us", "them", "it", "its",
    # Common job/CV words
    "experience", "years", "year", "skill", "skills", "knowledge", "ability", "responsibilities",
    "requirements", "required", "preferred", "looking", "seeking", "work", "working", "team",
    "developer", "engineer", "software",
    # Ukrainian/Russian
    "та", "і", "й", "або", "в", "у", "на", "для", "з", "по", "до", "це", "як", "що", "не",
    "років", "роки", "рік", "досвід", "вимоги", "обов", "язки",
}


def _tokenize(text: str) -> set[str]:
    # Keep + and # for things like C++ / C#.
    words = re.findall(r"[A-Za-zА-Яа-яЇїІіЄєҐґ0-9][A-Za-zА-Яа-яЇїІіЄєҐґ0-9+#.]{1,}", text.lower())
    tokens = set()
    for w in words:
        w = w.strip("._")
        if not w or len(w) <= 1:
            continue
        if w in _STOPWORDS:
            continue
        tokens.add(w)
    return tokens


def _job_text(job: Any) -> str:
    parts = [
        getattr(job, "job_title", "") or "",
        getattr(job, "company_name", "") or "",
        getattr(job, "location", "") or "",
        getattr(job, "work_type", "") or "",
        getattr(job, "role_summary", "") or "",
        getattr(job, "required_quals", "") or "",
        getattr(job, "preferred_quals", "") or "",
        getattr(job, "tools_and_methods", "") or "",
        getattr(job, "language_requirements", "") or "",
        getattr(job, "full_text", "") or "",
    ]
    return "\n".join(p for p in parts if p)


def _cv_text(cv: Any) -> str:
    parts = [
        getattr(cv, "job_title", "") or "",
        getattr(cv, "profile_summary", "") or "",
        getattr(cv, "programming_skills", "") or "",
        getattr(cv, "tools_and_tech", "") or "",
        getattr(cv, "other_skills", "") or "",
        getattr(cv, "projects", "") or "",
        getattr(cv, "education", "") or "",
        getattr(cv, "additional_info", "") or "",
        getattr(cv, "all_text", "") or "",
    ]
    return "\n".join(p for p in parts if p)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass(frozen=True, slots=True)
class MatchItem:
    job_id: str
    job_title: str
    source_url: str | None
    score: float  # 0..1
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "source_url": self.source_url,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def _heuristic_job_analysis(cv: Any, job: Any, item: MatchItem) -> dict[str, Any]:
    """Deterministic analysis for a single job (no OpenAI).

    Returns both a simple text summary (for logs) and a richer HTML/Markdown
    breakdown (for the UI), similar in spirit to backend/data/cv_job_analysis.md.
    """

    cv_tokens = _tokenize(_cv_text(cv))
    job_tokens = _tokenize(_job_text(job))
    common = sorted(list(cv_tokens & job_tokens))

    why = []
    if common:
        why.append("Overlap skills/keywords: " + ", ".join(common[:20]))

    bucket = getattr(cv, "experience_bucket", None)
    title = (getattr(job, "job_title", "") or "").lower()
    gaps = []
    if bucket in {"0-1", "1-3"} and any(k in title for k in ["senior", "lead", "principal"]):
        gaps.append("Role looks senior/lead; may require more years of experience.")

    if not common:
        gaps.append("Not enough overlapping keywords detected (job text may be short).")

    next_steps = [
        "Add 3–5 bullet points of concrete achievements to CV (impact + numbers).",
        "Mirror the vacancy keywords in your CV Skills/Projects section (truthfully).",
        "If you have <1 year exp, prioritize Junior/Intern roles and show pet projects." ,
    ]

    summary = (
        f"Heuristic analysis for job #{item.job_id} (score {item.score:.0%}).\n"
        + ("\n".join(why) if why else "")
        + ("\n\nPotential gaps:\n- " + "\n- ".join(gaps) if gaps else "")
        + "\n\nNext steps:\n- " + "\n- ".join(next_steps)
    ).strip()

    rich = _render_job_analysis_html(cv, job, item)

    return {
        "method": "heuristic",
        "job_id": item.job_id,
        "score": item.score,
        "summary": summary,
        "reasons": item.reasons,
        "breakdown": rich["breakdown"],
        "html": rich["html"],
        "markdown": rich["markdown"],
    }


def analyze_job(cv: Any, job: Any) -> dict[str, Any]:
    """Analyze a single job vs CV.

    Returns heuristic analysis by default; OpenAI analysis is opt-in.
    """

    item = score_job(cv, job)

    if not _openai_available():
        return _heuristic_job_analysis(cv, job, item)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        cv_text = _cv_text(cv)[:6000]
        job_text = _job_text(job)[:6000]
        prompt = (
            "You are a CV↔Job matching assistant. Compare this CV to this job posting.\n"
            "Produce a structured analysis similar to a recruiter screen.\n\n"
            "Return ONLY JSON with keys:\n"
            "{\n"
            '  "overall": "string",\n'
            '  "requirements": [\n'
            "    {\n"
            '      "requirement": "string",\n'
            '      "cv_match": "yes|partial|no",\n'
            '      "evidence": "string"\n'
            "    }\n"
            "  ],\n"
            '  "gaps": ["string"],\n'
            '  "recommendations": ["string"],\n'
            '  "cv_edits": ["string"],\n'
            '  "interview_prep": ["string"]\n'
            "}\n\n"
            f"Match score (heuristic): {item.score:.2f}\n\n"
            "CV:\n" + cv_text + "\n\n"
            "JOB:\n" + job_text
        )

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MATCH_MODEL", os.getenv("OPENAI_CV_MODEL", "gpt-4o-mini")),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content or "{}"
        import json

        data = json.loads(content)

        req_rows = []
        for r in (data.get("requirements") or []):
            req_rows.append({
                "requirement": str(r.get("requirement") or ""),
                "status": "✅" if str(r.get("cv_match") or "").lower() == "yes" else ("⚠️" if str(r.get("cv_match") or "").lower() == "partial" else "❌"),
                "evidence": str(r.get("evidence") or ""),
            })
        if not req_rows:
            # fallback to heuristic requirement extraction
            req_rows, _ = _build_requirements_table(cv, job)

        title = html.escape(getattr(job, "job_title", "") or "")
        url = html.escape(getattr(job, "source_url", "") or "")
        table_html = _render_table_html(req_rows)
        gaps = [str(x) for x in (data.get("gaps") or [])]
        recs = [str(x) for x in (data.get("recommendations") or [])]

        gaps_html = "<ul>" + "".join(f"<li>{html.escape(g)}</li>" for g in gaps[:10]) + "</ul>" if gaps else "<div class='muted'>—</div>"
        recs_html = "<ul>" + "".join(f"<li>{html.escape(r)}</li>" for r in recs[:10]) + "</ul>" if recs else "<div class='muted'>—</div>"
        cv_edits = [str(x) for x in (data.get("cv_edits") or [])]
        interview = [str(x) for x in (data.get("interview_prep") or [])]

        summary = str(data.get("overall") or "").strip()
        html_out = (
            f"<div class='analysis-head'><div class='analysis-title'>{title}</div>"
            f"<div class='analysis-meta'>Score: {item.score:.0%} • Method: openai</div>"
            + (f"<div class='analysis-url'><a href='{url}' target='_blank' rel='noreferrer'>{url}</a></div>" if url else "")
            + "</div>"
            + (f"<p>{html.escape(summary)}</p>" if summary else "")
            + "<h4>Requirements vs CV</h4>" + table_html
            + "<h4>Gaps</h4>" + gaps_html
            + "<h4>Recommendations</h4>" + recs_html
            + ("<h4>CV edits</h4><ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in cv_edits[:10]) + "</ul>" if cv_edits else "")
            + ("<h4>Interview prep</h4><ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in interview[:10]) + "</ul>" if interview else "")
        )

        return {
            "method": "openai",
            "job_id": item.job_id,
            "score": item.score,
            "summary": summary,
            "reasons": item.reasons,
            "openai": data,
            "html": html_out,
            "markdown": "",  # optional; UI uses HTML
        }
    except Exception as e:
        # Fall back
        out = _heuristic_job_analysis(cv, job, item)
        out["summary"] = out["summary"] + f"\n\n(OpenAI failed, fallback to heuristic. Error: {e})"
        return out


def score_job(cv: Any, job: Any) -> MatchItem:
    """Heuristic score: token overlap + small rule-based adjustments."""

    cv_tokens = _tokenize(_cv_text(cv))
    job_tokens = _tokenize(_job_text(job))

    common = cv_tokens & job_tokens

    # Base similarity: Jaccard, but softened to behave with short texts.
    denom = max(1, len(cv_tokens) + len(job_tokens) - len(common))
    jacc = len(common) / denom

    reasons: list[str] = []
    if common:
        # show a few signals
        sample = sorted(list(common))[:10]
        reasons.append("keyword overlap: " + ", ".join(sample))

    # Category alignment bonus (Python/PHP/PM/Product). Helps when job text is short.
    cls = classify_cv(_cv_text(cv))
    if cls.category.lower() in (getattr(job, "job_title", "") or "").lower():
        jacc += 0.03
        reasons.append(f"title mentions category '{cls.category}'")

    # Experience bucket adjustment based on title keywords
    bucket = getattr(cv, "experience_bucket", None)
    title = (getattr(job, "job_title", "") or "").lower()
    if bucket in {"0-1", "1-3"}:
        if any(k in title for k in ["junior", "entry", "intern", "trainee"]):
            jacc += 0.05
            reasons.append("junior/entry-level hint in title")
        if any(k in title for k in ["senior", "lead", "principal"]):
            jacc -= 0.08
            reasons.append("senior/lead hint in title (penalty for low exp)")

    # Clamp then map through a sigmoid to get nicer distribution.
    jacc = max(0.0, min(1.0, jacc))
    score = _sigmoid((jacc - 0.08) * 10.0)

    return MatchItem(
        job_id=str(getattr(job, "id")),
        job_title=str(getattr(job, "job_title", "") or ""),
        source_url=getattr(job, "source_url", None),
        score=float(max(0.0, min(1.0, score))),
        reasons=reasons,
    )


def rank_jobs(cv: Any, jobs: Iterable[Any], *, limit: int | None = None) -> list[MatchItem]:
    items = [score_job(cv, j) for j in jobs]
    items.sort(key=lambda x: x.score, reverse=True)
    if limit is not None:
        return items[: max(0, int(limit))]
    return items


def _openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and os.getenv("OPENAI_MATCHER", "0") == "1"


def build_report(
    cv: Any,
    ranked: list[MatchItem],
    jobs_by_id: dict[int, Any],
    *,
    top_n: int = 10,
) -> dict[str, Any]:
    """Return a narrative report.

    If OpenAI is disabled/unavailable, returns a deterministic template.
    """

    top = ranked[: max(1, int(top_n))]

    if not _openai_available():
        summary = (
            "OpenAI report is disabled. Showing heuristic ranking based on keyword overlap "
            "between your CV and the job titles/descriptions stored in the DB. "
            "Enable OPENAI_MATCHER=1 to get a detailed narrative analysis."
        )
        return {
            "method": "heuristic",
            "summary": summary,
            "top": [i.to_dict() for i in top],
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        cv_text = _cv_text(cv)
        # Keep prompt compact: include CV + top job snippets.
        job_lines: list[str] = []
        for i in top:
            job = jobs_by_id.get(i.job_id)
            snippet = _job_text(job) if job is not None else i.job_title
            snippet = snippet[:2000]
            job_lines.append(
                f"JOB id={i.job_id} score={i.score:.2f}\nTitle: {i.job_title}\nURL: {i.source_url or ''}\nText:\n{snippet}\n"
            )

        prompt = (
            "You are a career assistant. Analyze the candidate CV and the job postings.\n"
            "Your tasks:\n"
            "1) Pick the best matching jobs for this CV.\n"
            "2) Explain why they match, and what gaps exist.\n"
            "3) Provide an actionable plan: what to improve in CV or skills to increase matches.\n\n"
            "Return ONLY JSON with keys:\n"
            "{\n"
            '  "overall": "string",\n'
            '  "top_matches": [\n'
            "     {\n"
            '       "job_id": number,\n'
            '       "score": number,\n'
            '       "why_match": "string",\n'
            '       "gaps": "string",\n'
            '       "next_steps": "string"\n'
            "     }\n"
            "  ]\n"
            "}\n\n"
            "CV:\n" + cv_text[:6000] + "\n\n" + "JOBS:\n" + "\n".join(job_lines)
        )

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MATCH_MODEL", os.getenv("OPENAI_CV_MODEL", "gpt-4o-mini")),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content or "{}"
        import json

        data = json.loads(content)
        return {
            "method": "openai",
            "summary": data.get("overall") or "",
            "top": [i.to_dict() for i in top],
            "openai": data,
        }
    except Exception as e:
        return {
            "method": "heuristic",
            "summary": f"OpenAI report failed, falling back to heuristic. Error: {e}",
            "top": [i.to_dict() for i in top],
        }

