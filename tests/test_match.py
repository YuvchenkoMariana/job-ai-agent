import pytest
from fastapi.testclient import TestClient

from backend.db.database import Session, JobPosting, JobRun, JobRunJob, UsersCv, init_db, utc_now_minute, GUEST_USER_UUID
from server.fast_api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_db():
    init_db()
    with Session() as session:
        session.query(JobRunJob).delete()
        session.query(JobRun).delete()
        session.query(JobPosting).delete()
        session.query(UsersCv).delete()
        session.commit()
    yield
    with Session() as session:
        session.query(JobRunJob).delete()
        session.query(JobRun).delete()
        session.query(JobPosting).delete()
        session.query(UsersCv).delete()
        session.commit()


def test_match_scores_requires_cv():
    res = client.get("/api/match/scores")
    assert res.status_code == 404


def test_match_scores_returns_ranked_items():
    with Session() as session:
        cv = UsersCv(
            job_title="Python Developer",
            all_text="Python Flask Django",
            experience_bucket="0-1",
            last_used_at=utc_now_minute(),
        )
        session.add(cv)
        session.flush()
        j1 = JobPosting(job_title="Junior Python Developer", source_url="https://jobs.dou.ua/1")
        j2 = JobPosting(job_title="Senior Java Engineer", source_url="https://jobs.dou.ua/2")
        session.add_all([j1, j2])
        session.flush()

        # Create a run snapshot so /api/match/* has a job set to work with.
        run = JobRun(user_id=GUEST_USER_UUID, cv_id=cv.id, cv_hash=cv.cv_hash, jobs_hash="test", created_at=utc_now_minute())
        session.add(run)
        session.flush()
        session.add_all([
            JobRunJob(run_id=run.id, job_id=j1.id),
            JobRunJob(run_id=run.id, job_id=j2.id),
        ])
        session.commit()

    res = client.get("/api/match/scores?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total_jobs"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["job_title"] in {"Junior Python Developer", "Senior Java Engineer"}
    assert 0.0 <= float(data["items"][0]["score"]) <= 1.0


def test_match_report_returns_summary():
    with Session() as session:
        cv = UsersCv(
            job_title="Python Developer",
            all_text="Python Flask Django",
            experience_bucket="0-1",
            last_used_at=utc_now_minute(),
        )
        session.add(cv)
        session.flush()
        j1 = JobPosting(job_title="Junior Python Developer", source_url="https://jobs.dou.ua/1")
        session.add(j1)
        session.flush()
        run = JobRun(user_id=GUEST_USER_UUID, cv_id=cv.id, cv_hash=cv.cv_hash, jobs_hash="test", created_at=utc_now_minute())
        session.add(run)
        session.flush()
        session.add(JobRunJob(run_id=run.id, job_id=j1.id))
        session.commit()

    res = client.get("/api/match/report?top_n=5")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "top" in data
    assert data["total_jobs"] == 1


def test_match_job_analysis_endpoint():
    with Session() as session:
        cv = UsersCv(
            job_title="Python Developer",
            all_text="Python Flask Django",
            experience_bucket="0-1",
            last_used_at=utc_now_minute(),
        )
        session.add(cv)
        session.flush()
        job = JobPosting(job_title="Junior Python Developer", source_url="https://jobs.dou.ua/1")
        session.add(job)
        session.flush()
        run = JobRun(user_id=GUEST_USER_UUID, cv_id=cv.id, cv_hash=cv.cv_hash, jobs_hash="test", created_at=utc_now_minute())
        session.add(run)
        session.flush()
        session.add(JobRunJob(run_id=run.id, job_id=job.id))
        session.commit()
        job_id = str(job.id)

    res = client.get(f"/api/match/job/{job_id}/analysis")
    assert res.status_code == 200
    data = res.json()
    assert data["job"]["id"] == job_id
    assert "summary" in data
    assert "html" in data
    assert "<table" in (data["html"] or "")
    assert 0.0 <= float(data["score"]) <= 1.0

