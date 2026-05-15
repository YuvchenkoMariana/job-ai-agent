const test = require("node:test");
const assert = require("node:assert/strict");

const { JobDescriptionExtension, JobDescriptionList } = require("../dist/job");

test("JobDescriptionExtension deserializes from object", () => {
  const payload = {
    job_title: "Lead Python Engineer",
    source_url: "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
  };

  const job = JobDescriptionExtension.fromDict(payload);

  assert.equal(job.job_title, payload.job_title);
  assert.equal(job.source_url, payload.source_url);
});

test("JobDescriptionExtension serializes to object", () => {
  const job = new JobDescriptionExtension({
    job_title: "Senior Python developer(with React)",
    source_url: "https://jobs.dou.ua/companies/techery/vacancies/356043/",
  });

  const dict = job.toDict();
  assert.equal(dict.job_title, "Senior Python developer(with React)");
  assert.equal(dict.source_url, "https://jobs.dou.ua/companies/techery/vacancies/356043/");
});

test("JobDescriptionExtension round-trip serialize/deserialize", () => {
  const payload = {
    job_title: "Python/AI engineer",
    source_url: "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
  };

  const job = JobDescriptionExtension.fromDict(payload);
  const reconstructed = JobDescriptionExtension.fromDict(job.toDict());

  assert.equal(reconstructed.job_title, payload.job_title);
  assert.equal(reconstructed.source_url, payload.source_url);
});

test("JobDescriptionList.fromList creates job objects", () => {
  const data = [
    { job_title: "Backend Dev", source_url: "https://example.com/1" },
    { job_title: "Frontend Dev", source_url: "https://example.com/2" },
  ];

  const jdl = JobDescriptionList.fromList(data);

  assert.equal(jdl.jobs.length, 2);
  assert.ok(jdl.jobs[0] instanceof JobDescriptionExtension);
  assert.equal(jdl.jobs[0].job_title, "Backend Dev");
  assert.equal(jdl.jobs[1].source_url, "https://example.com/2");
});

test("JobDescriptionList.toList returns dicts", () => {
  const jdl = new JobDescriptionList([
    new JobDescriptionExtension({ job_title: "Dev A", source_url: "https://a.com" }),
    new JobDescriptionExtension({ job_title: "Dev B", source_url: "https://b.com" }),
  ]);

  const result = jdl.toList();

  assert.ok(Array.isArray(result));
  assert.equal(result.length, 2);
  assert.equal(typeof result[0], "object");
  assert.equal(result[0].job_title, "Dev A");
  assert.equal(result[1].source_url, "https://b.com");
});

test("JobDescriptionList round-trip JSON serialize/deserialize", () => {
  const payload = {
    jobs: [
      {
        job_title: "Lead Python Engineer",
        source_url: "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/",
      },
      {
        job_title: "Python/AI engineer",
        source_url: "https://jobs.dou.ua/companies/rolique/vacancies/356174/",
      },
    ],
  };

  const jobs = JobDescriptionList.fromJson(JSON.stringify(payload));
  const jsonOut = jobs.toJson();
  const reconstructed = JobDescriptionList.fromJson(jsonOut);

  assert.equal(jobs.jobs.length, 2);
  assert.equal(jobs.jobs[0].job_title, "Lead Python Engineer");
  assert.equal(reconstructed.jobs[1].source_url, "https://jobs.dou.ua/companies/rolique/vacancies/356174/");
});

test("JobDescriptionList.fromJson throws for invalid payload", () => {
  const invalidJsonPayload = JSON.stringify({
    job_title: "Not a list",
    source_url: "https://example.com",
  });

  assert.throws(
    () => JobDescriptionList.fromJson(invalidJsonPayload),
    /Expected a JSON object with 'jobs' key or a JSON array/
  );
});

test("JobDescriptionList empty list serializes to empty JSON object", () => {
  const jdl = new JobDescriptionList([]);

  assert.equal(jdl.toJson(), '{"jobs":[]}');
  assert.deepEqual(jdl.toList(), []);
});

test("JobDescriptionList.fromJson preserves required fields", () => {
  const payload = {
    jobs: [
      {
        job_title: "Senior Dev",
        source_url: "https://example.com/job",
      },
    ],
  };

  const jdl = JobDescriptionList.fromJson(JSON.stringify(payload));
  const job = jdl.jobs[0];

  assert.equal(job.job_title, "Senior Dev");
  assert.equal(job.source_url, "https://example.com/job");
});

test("JobDescriptionList.fromJson accepts array for backwards compat", () => {
  const payload = [{ job_title: "Dev", source_url: "https://x.com" }];

  const jdl = JobDescriptionList.fromJson(JSON.stringify(payload));

  assert.equal(jdl.jobs.length, 1);
  assert.equal(jdl.jobs[0].job_title, "Dev");
});

test("JobDescriptionList.toJson preserves unicode", () => {
  const jdl = new JobDescriptionList([
    new JobDescriptionExtension({
      job_title: "Розробник Python",
      source_url: "https://dou.ua/вакансія",
    }),
  ]);

  const jsonStr = jdl.toJson();
  assert.ok(jsonStr.includes("Розробник Python"));
  assert.ok(jsonStr.includes("https://dou.ua/вакансія"));

  const restored = JobDescriptionList.fromJson(jsonStr);
  assert.equal(restored.jobs[0].job_title, "Розробник Python");
});
