const test = require("node:test");
const assert = require("node:assert/strict");

const { JobDescription, JobDescriptionList } = require("../job");

test("JobDescription deserializes from object", () => {
  const payload = {
    id: 356182,
    title: "Lead Python Engineer",
    href: "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
  };

  const job = JobDescription.fromDict(payload);

  assert.equal(job.id, payload.id);
  assert.equal(job.title, payload.title);
  assert.equal(job.href, payload.href);
});

test("JobDescription serializes to object", () => {
  const job = new JobDescription({
    id: 20,
    title: "Senior Python developer(with React)",
    href: "https://jobs.dou.ua/companies/techery/vacancies/356043/",
  });

  assert.deepEqual(job.toDict(), {
    id: 20,
    title: "Senior Python developer(with React)",
    href: "https://jobs.dou.ua/companies/techery/vacancies/356043/",
  });
});

test("JobDescription round-trip serialize/deserialize", () => {
  const payload = {
    id: 356174,
    title: "Python/AI engineer",
    href: "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
  };

  const job = JobDescription.fromDict(payload);
  const reconstructed = JobDescription.fromDict(job.toDict());

  assert.deepEqual(reconstructed.toDict(), payload);
});

test("JobDescriptionList round-trip list serialize/deserialize", () => {
  const payload = [
    {
      id: 356182,
      title: "Lead Python Engineer",
      href: "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
    },
    {
      id: 356174,
      title: "Python/AI engineer",
      href: "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
    },
  ];

  const jobs = JobDescriptionList.fromList(payload);
  const reconstructed = JobDescriptionList.fromList(jobs.toList());

  assert.deepEqual(jobs.toList(), payload);
  assert.deepEqual(reconstructed.toList(), payload);
});

test("JobDescriptionList round-trip JSON serialize/deserialize", () => {
  const payload = [
    {
      id: 356182,
      title: "Lead Python Engineer",
      href: "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
    },
    {
      id: 356174,
      title: "Python/AI engineer",
      href: "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
    },
  ];

  const jobs = JobDescriptionList.fromJson(JSON.stringify(payload));
  const jsonOut = jobs.toJson();
  const reconstructed = JobDescriptionList.fromJson(jsonOut);

  assert.deepEqual(jobs.toList(), payload);
  assert.deepEqual(JSON.parse(jsonOut), payload);
  assert.deepEqual(reconstructed.toList(), payload);
});

test("JobDescriptionList.fromJson throws for non-array payload", () => {
  const invalidJsonPayload = JSON.stringify({
    id: 1,
    title: "Not a list",
    href: "https://example.com",
  });

  assert.throws(
    () => JobDescriptionList.fromJson(invalidJsonPayload),
    /Expected a JSON array of job descriptions/
  );
});

