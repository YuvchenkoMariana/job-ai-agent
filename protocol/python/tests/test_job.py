import unittest
import json

from protocol.python.job import JobDescriptionList, JobDescriptionExtension


class TestJobDescriptionListSerialization(unittest.TestCase):
    def test_round_trip_json_string(self) -> None:
        payload = {"jobs": [
            {"job_title": "Lead Python Engineer", "source_url": "https://jobs.dou.ua/1"},
            {"job_title": "Python/AI engineer", "source_url": "https://jobs.dou.ua/2"},
        ]}
        jobs = JobDescriptionList.from_json(json.dumps(payload))
        reconstructed = JobDescriptionList.from_json(jobs.to_json())
        self.assertEqual(reconstructed, jobs)

    def test_from_json_raises_for_invalid_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "Expected a JSON object with 'jobs' key or a JSON array"):
            JobDescriptionList.from_json('{"job_title": "x", "source_url": "y"}')

    def test_from_list_creates_job_objects(self) -> None:
        data = [
            {"job_title": "Backend Dev", "source_url": "https://example.com/1"},
            {"job_title": "Frontend Dev", "source_url": "https://example.com/2"},
        ]
        jdl = JobDescriptionList.from_list(data)
        self.assertEqual(len(jdl.jobs), 2)
        self.assertIsInstance(jdl.jobs[0], JobDescriptionExtension)
        self.assertEqual(jdl.jobs[0].job_title, "Backend Dev")
        self.assertEqual(jdl.jobs[1].source_url, "https://example.com/2")

    def test_to_list_returns_dicts(self) -> None:
        jdl = JobDescriptionList(jobs=[
            JobDescriptionExtension(job_title="Dev A", source_url="https://a.com"),
            JobDescriptionExtension(job_title="Dev B", source_url="https://b.com"),
        ])
        result = jdl.to_list()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]["job_title"], "Dev A")
        self.assertEqual(result[1]["source_url"], "https://b.com")

    def test_to_json_produces_valid_json(self) -> None:
        jdl = JobDescriptionList(jobs=[
            JobDescriptionExtension(job_title="Engineer", source_url="https://x.com/1"),
        ])
        json_str = jdl.to_json()
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, dict)
        self.assertIn("jobs", parsed)
        self.assertEqual(parsed["jobs"][0]["job_title"], "Engineer")

    def test_from_json_preserves_required_fields(self) -> None:
        payload = {"jobs": [
            {
                "job_title": "Senior Dev",
                "source_url": "https://example.com/job",
            }
        ]}
        jdl = JobDescriptionList.from_json(json.dumps(payload))
        job = jdl.jobs[0]
        self.assertEqual(job.job_title, "Senior Dev")
        self.assertEqual(job.source_url, "https://example.com/job")

    def test_round_trip_extension(self) -> None:
        jdl = JobDescriptionList(jobs=[
            JobDescriptionExtension(
                job_title="ML Engineer",
                source_url="https://example.com/ml",
            ),
        ])
        json_str = jdl.to_json()
        restored = JobDescriptionList.from_json(json_str)
        self.assertEqual(restored, jdl)

    def test_empty_list_serializes_to_empty_json_object(self) -> None:
        jdl = JobDescriptionList(jobs=[])
        self.assertEqual(jdl.to_json(), '{"jobs": []}')
        self.assertEqual(jdl.to_list(), [])

    def test_from_json_empty_jobs(self) -> None:
        jdl = JobDescriptionList.from_json('{"jobs": []}')
        self.assertEqual(len(jdl.jobs), 0)

    def test_from_json_accepts_array_for_backwards_compat(self) -> None:
        jdl = JobDescriptionList.from_json('[{"job_title": "Dev", "source_url": "https://x.com"}]')
        self.assertEqual(len(jdl.jobs), 1)
        self.assertEqual(jdl.jobs[0].job_title, "Dev")

    def test_to_json_preserves_unicode(self) -> None:
        jdl = JobDescriptionList(jobs=[
            JobDescriptionExtension(job_title="Розробник Python", source_url="https://dou.ua/вакансія"),
        ])
        json_str = jdl.to_json()
        self.assertIn("Розробник Python", json_str)
        self.assertIn("https://dou.ua/вакансія", json_str)
        restored = JobDescriptionList.from_json(json_str)
        self.assertEqual(restored.jobs[0].job_title, "Розробник Python")


if __name__ == "__main__":
    unittest.main()
