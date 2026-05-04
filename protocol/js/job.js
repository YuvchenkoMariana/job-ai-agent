class JobDescription {
  constructor({ id, title, href }) {
    this.id = Number(id);
    this.title = String(title);
    this.href = String(href);
  }

  static fromDict(data) {
    return new JobDescription(data);
  }

  toDict() {
    return {
      id: this.id,
      title: this.title,
      href: this.href,
    };
  }
}

class JobDescriptionList {
  constructor(jobs) {
    this.jobs = jobs;
  }

  static fromList(data) {
    if (!Array.isArray(data)) {
      throw new Error("Expected an array of job descriptions");
    }

    return new JobDescriptionList(data.map((item) => JobDescription.fromDict(item)));
  }

  static fromJson(data) {
    const parsed = JSON.parse(data);
    if (!Array.isArray(parsed)) {
      throw new Error("Expected a JSON array of job descriptions");
    }

    return JobDescriptionList.fromList(parsed);
  }

  toList() {
    return this.jobs.map((job) => job.toDict());
  }

  toJson() {
    return JSON.stringify(this.toList());
  }
}

module.exports = {
  JobDescription,
  JobDescriptionList,
};

