import unittest

from server.fast_api import JobDescription


class TestJobDescriptionSerialization(unittest.TestCase):
    def test_deserialize_from_dict(self) -> None:
        payload = {
            "job_title": "Lead Python Engineer",
            "source_url": "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
            "id": "356182",
        }
        job = JobDescription.from_dict(payload)
        self.assertEqual(job.job_title, payload["job_title"])
        self.assertEqual(job.source_url, payload["source_url"])
        self.assertEqual(job.id, "356182")

    def test_deserialize_from_dict_int_id_coerced_to_str(self) -> None:
        """from_dict always converts id to str, even when the input is an int."""
        payload = {
            "job_title": "Lead Python Engineer",
            "source_url": "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
            "id": 356182,
        }
        job = JobDescription.from_dict(payload)
        self.assertEqual(job.id, "356182")

    def test_serialize_to_dict(self) -> None:
        job = JobDescription(
            job_title="Senior Python developer(with React)",
            source_url="https://jobs.dou.ua/companies/techery/vacancies/356043/",
            id="20",
        )
        d = job.to_dict()
        self.assertEqual(d["job_title"], "Senior Python developer(with React)")
        self.assertEqual(d["source_url"], "https://jobs.dou.ua/companies/techery/vacancies/356043/")
        self.assertEqual(d["id"], "20")

    def test_optional_fields_default_to_none(self) -> None:
        job = JobDescription(job_title="Dev", source_url="https://example.com")
        self.assertIsNone(job.company_name)
        self.assertIsNone(job.salary_min)
        self.assertIsNone(job.location)

    def test_salary_currency_defaults_to_usd(self) -> None:
        job = JobDescription(job_title="Dev", source_url="https://example.com")
        self.assertEqual(job.salary_currency, "USD")

    def test_round_trip_serialize_deserialize(self) -> None:
        payload = {
            "job_title": "Senior Python Engineer",
            "source_url": "https://jobs.dou.ua/vacancies/348942/",
            "id": "348942",
            "company_name": "AirLogix",
            "location": "Remote",
        }
        job = JobDescription.from_dict(payload)
        reconstructed = JobDescription.from_dict(job.to_dict())
        self.assertEqual(reconstructed, job)

    def test_round_trip_serialize_deserialize_list(self) -> None:
        payload = [
            {
                "job_title": "Lead Python Engineer",
                "source_url": "https://jobs.dou.ua/vacancies/356182/",
                "id": "356182",
            },
            {
                "job_title": "Python/AI engineer",
                "source_url": "https://jobs.dou.ua/vacancies/356174/",
                "id": "356174",
            },
        ]
        jobs = [JobDescription.from_dict(item) for item in payload]
        reconstructed = [JobDescription.from_dict(j.to_dict()) for j in jobs]
        self.assertEqual(reconstructed, jobs)


if __name__ == "__main__":
    unittest.main()
