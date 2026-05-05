"""
Tests for server/fast_api.py  — uses FastAPI TestClient (synchronous).
Run with:  pytest tests/test_api.py -v
"""
import pytest
from fastapi.testclient import TestClient

from protocol.python.job import JobDescriptionExtension, JobDescriptionList
from server.fast_api import app, _clear_jobs_db
from backend.db.database import init_db


@pytest.fixture(autouse=True)
def clear_store():
    """Initialise DB and wipe job_vacancies before/after every test."""
    init_db()
    _clear_jobs_db()
    yield
    _clear_jobs_db()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper — build payload in JobDescriptionList format: {"jobs": [...]}
# ---------------------------------------------------------------------------

def make_payload(*jobs: dict) -> dict:
    """Wraps job dicts into the JobDescriptionList format: {"jobs": [...]}"""
    return {"jobs": list(jobs)}


# ---------------------------------------------------------------------------
# GET /api/jobs
# ---------------------------------------------------------------------------

class TestGetJobs:
    def test_returns_empty_list_initially(self):
        res = client.get("/api/jobs")
        assert res.status_code == 200
        assert res.json() == []

    def test_returns_jobs_after_sync(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Python Dev", "source_url": "https://jobs.dou.ua/1"},
            {"job_title": "Go Dev",     "source_url": "https://jobs.dou.ua/2"},
        ))
        res = client.get("/api/jobs")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["job_title"] == "Python Dev"
        assert data[0]["source_url"] == "https://jobs.dou.ua/1"
        assert data[1]["job_title"] == "Go Dev"
        assert data[1]["source_url"] == "https://jobs.dou.ua/2"

    def test_jobs_are_ordered_by_id(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "A", "source_url": "https://jobs.dou.ua/1"},
            {"job_title": "B", "source_url": "https://jobs.dou.ua/2"},
        ))
        ids = [j["id"] for j in client.get("/api/jobs").json()]
        assert ids == sorted(ids)

    def test_response_includes_all_fields(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Dev", "source_url": "https://jobs.dou.ua/1"},
        ))
        job = client.get("/api/jobs").json()[0]
        expected_keys = {
            "id", "job_title", "source_url", "company_name", "company_overview",
            "location", "work_type", "role_summary", "responsibilities",
            "required_quals", "preferred_quals", "tools_and_methods",
            "what_success_looks", "salary_min", "salary_max", "salary_currency",
            "language_requirements",
        }
        assert expected_keys == set(job.keys())


# ---------------------------------------------------------------------------
# POST /api/jobs/sync
# ---------------------------------------------------------------------------

class TestSyncJobs:
    def test_returns_count(self):
        res = client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Dev", "source_url": "https://jobs.dou.ua/1"},
        ))
        assert res.status_code == 200
        assert res.json() == {"count": 1}

    def test_upserts_existing_job_by_source_url(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Old Title", "source_url": "https://jobs.dou.ua/1"},
        ))
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "New Title", "source_url": "https://jobs.dou.ua/1"},
        ))
        data = client.get("/api/jobs").json()
        assert len(data) == 1
        assert data[0]["job_title"] == "New Title"

    def test_inserts_new_job_with_different_url(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Job A", "source_url": "https://jobs.dou.ua/1"},
        ))
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Job B", "source_url": "https://jobs.dou.ua/2"},
        ))
        assert len(client.get("/api/jobs").json()) == 2

    def test_filters_out_empty_jobs(self):
        res = client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "",          "source_url": ""},
            {"job_title": "Valid Job", "source_url": "https://jobs.dou.ua/2"},
        ))
        assert res.json() == {"count": 1}

    def test_trims_whitespace(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "  Spacey  ", "source_url": "  https://jobs.dou.ua/1  "},
        ))
        data = client.get("/api/jobs").json()
        assert data[0]["job_title"] == "Spacey"
        assert data[0]["source_url"] == "https://jobs.dou.ua/1"

    def test_empty_payload_returns_422(self):
        assert client.post("/api/jobs/sync", json={"jobs": []}).status_code == 422

    def test_salary_currency_defaults_to_usd(self):
        client.post("/api/jobs/sync", json=make_payload(
            {"job_title": "Dev", "source_url": "https://jobs.dou.ua/1"},
        ))
        assert client.get("/api/jobs").json()[0]["salary_currency"] == "USD"
    
    def test_sync_batch_via_job_description_list(self):
        jl = JobDescriptionList([
            JobDescriptionExtension(
                job_title="VBA / Python Developer (Automation & Legacy Modernization)",
                source_url="https://jobs.dou.ua/companies/intelvision/vacancies/356809/",
            ),
        ])

        res = client.post(
            "/api/jobs/sync",
            content=jl.to_json(),
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 200
        assert res.json() == {"count": 1}

        jobs = client.get("/api/jobs").json()
        assert len(jobs) == 1
        assert jobs[0]["job_title"] == "VBA / Python Developer (Automation & Legacy Modernization)"
        assert jobs[0]["source_url"] == "https://jobs.dou.ua/companies/intelvision/vacancies/356809/"

