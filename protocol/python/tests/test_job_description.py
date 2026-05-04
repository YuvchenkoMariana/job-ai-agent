import unittest
import json

from protocol.python.job import JobDescription, JobDescriptionList


class TestJobDescriptionSerialization(unittest.TestCase):
    def test_deserialize_from_dict(self) -> None:
        payload = {
            "id": 356182,
            "title": "Lead Python Engineer",
            "href": "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
        }

        job = JobDescription.from_dict(payload)

        self.assertEqual(job.id, payload["id"])
        self.assertEqual(job.title, payload["title"])
        self.assertEqual(job.href, payload["href"])

    def test_serialize_to_dict(self) -> None:
        job = JobDescription(
            id=20,
            title="Senior Python developer(with React)",
            href="https://jobs.dou.ua/companies/techery/vacancies/356043/",
        )

        self.assertEqual(
            job.to_dict(),
            {
                "id": 20,
                "title": "Senior Python developer(with React)",
                "href": "https://jobs.dou.ua/companies/techery/vacancies/356043/",
            },
        )

    def test_round_trip_serialize_deserialize(self) -> None:
        payload = {
            "id": 348942,
            "title": "Senior С++/Python Software Engineer (Linux)",
            "href": "https://jobs.dou.ua/companies/airlogix/vacancies/348942/",
        }

        job = JobDescription.from_dict(payload)
        serialized = job.to_dict()
        reconstructed = JobDescription.from_dict(serialized)

        self.assertEqual(reconstructed, job)

    def test_round_trip_serialize_deserialize_list(self) -> None:
        payload = [
            {
                "id": 356182,
                "title": "Lead Python Engineer",
                "href": "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
            },
            {
                "id": 356174,
                "title": "Python/AI engineer",
                "href": "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
            },
        ]

        jobs = [JobDescription.from_dict(item) for item in payload]
        serialized = [job.to_dict() for job in jobs]
        reconstructed = [JobDescription.from_dict(item) for item in serialized]

        self.assertEqual(serialized, payload)
        self.assertEqual(reconstructed, jobs)


class TestJobDescriptionListSerialization(unittest.TestCase):
    def test_round_trip_json_string(self) -> None:
        payload = [
            {
                "id": 356182,
                "title": "Lead Python Engineer",
                "href": "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
            },
            {
                "id": 356174,
                "title": "Python/AI engineer",
                "href": "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
            },
        ]

        json_payload = json.dumps(payload)
        jobs = JobDescriptionList.from_json(json_payload)

        self.assertEqual(jobs.to_list(), payload)
        self.assertEqual(json.loads(jobs.to_json()), payload)

        reconstructed = JobDescriptionList.from_json(jobs.to_json())
        self.assertEqual(reconstructed, jobs)

    def test_from_json_raises_for_non_array_payload(self) -> None:
        invalid_json_payload = '{"id": 1, "title": "Not a list", "href": "https://example.com"}'

        with self.assertRaisesRegex(
            ValueError,
            "Expected a JSON array of job descriptions",
        ):
            JobDescriptionList.from_json(invalid_json_payload)


if __name__ == "__main__":
    unittest.main()

