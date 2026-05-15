import pytest
from fastapi.testclient import TestClient

from backend.db.database import Session, CvDocument, UsersCv, init_db
from server.fast_api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_cv_docs():
    """Ensure cv_documents table is clean for each test."""
    init_db()
    with Session() as session:
        session.query(CvDocument).delete()
        session.query(UsersCv).delete()
        session.commit()
    yield
    with Session() as session:
        session.query(CvDocument).delete()
        session.query(UsersCv).delete()
        session.commit()


def test_plugin_target_requires_cv():
    res = client.get("/api/plugin/dou-target")
    assert res.status_code == 404


@pytest.mark.parametrize(
    "cv_text, expected_category",
    [
        ("Petro Petrenko\nPHP Developer\n", "PHP"),
        ("Petro Petrenko\nPython Developer\n", "Python"),
        ("Product Manager\nExperience...", "Product Manager"),
        ("Project Manager\nExperience...", "Project Manager"),
    ],
)
def test_plugin_target_detects_category(cv_text: str, expected_category: str):
    # Upload CV
    res = client.post(
        "/api/cv/upload",
        files={"file": ("cv.md", cv_text.encode("utf-8"), "text/markdown")},
    )
    assert res.status_code == 200

    # Ask plugin target
    res2 = client.get("/api/plugin/dou-target")
    assert res2.status_code == 200
    data = res2.json()

    assert data["category"] == expected_category
    assert "dou_url" in data
    assert data["dou_url"].startswith("https://jobs.dou.ua/vacancies/?category=")


def test_plugin_target_includes_exp_bucket_for_entry_level():
    cv_text = "Python Developer (Entry Level)\nSkills: Python\n"
    res = client.post(
        "/api/cv/upload",
        files={"file": ("cv.md", cv_text.encode("utf-8"), "text/markdown")},
    )
    assert res.status_code == 200

    res2 = client.get("/api/plugin/dou-target")
    assert res2.status_code == 200
    data = res2.json()

    assert data["category"] == "Python"
    assert data["experience_bucket"] == "0-1"
    assert "exp=0-1" in data["dou_url"]


