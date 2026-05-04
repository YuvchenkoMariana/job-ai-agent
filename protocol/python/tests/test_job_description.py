import unittest

from protocol.python.job import JobDescription


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


if __name__ == "__main__":
    unittest.main()

