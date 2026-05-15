interface JobDescriptionExtensionData {
  job_title: string;
  source_url: string;
}

interface JobDescriptionListData {
  jobs: JobDescriptionExtensionData[];
}

class JobDescriptionExtension {
  readonly job_title: string;
  readonly source_url: string;

  constructor({ job_title, source_url }: JobDescriptionExtensionData) {
    this.job_title = String(job_title);
    this.source_url = String(source_url);
  }

  static fromDict(data: JobDescriptionExtensionData): JobDescriptionExtension {
    return new JobDescriptionExtension({
      job_title: data.job_title,
      source_url: data.source_url,
    });
  }

  toDict(): JobDescriptionExtensionData {
    return {
      job_title: this.job_title,
      source_url: this.source_url,
    };
  }
}

class JobDescriptionList {
  readonly jobs: JobDescriptionExtension[];

  constructor(jobs: JobDescriptionExtension[]) {
    this.jobs = jobs;
  }

  static fromList(data: JobDescriptionExtensionData[]): JobDescriptionList {
    if (!Array.isArray(data)) {
      throw new Error("Expected an array of job descriptions");
    }

    return new JobDescriptionList(data.map((item) => JobDescriptionExtension.fromDict(item)));
  }

  static fromDict(data: JobDescriptionListData): JobDescriptionList {
    if (!("jobs" in data)) {
      throw new Error("Expected an object with 'jobs' key");
    }
    return JobDescriptionList.fromList(data.jobs);
  }

  static fromJson(data: string): JobDescriptionList {
    const parsed = JSON.parse(data);
    if (typeof parsed === "object" && parsed !== null && "jobs" in parsed) {
      return JobDescriptionList.fromDict(parsed as JobDescriptionListData);
    }
    if (Array.isArray(parsed)) {
      return JobDescriptionList.fromList(parsed);
    }
    throw new Error("Expected a JSON object with 'jobs' key or a JSON array");
  }

  toList(): JobDescriptionExtensionData[] {
    return this.jobs.map((job) => job.toDict());
  }

  toDict(): JobDescriptionListData {
    return { jobs: this.toList() };
  }

  toJson(): string {
    return JSON.stringify(this.toDict());
  }
}

export { JobDescriptionExtensionData, JobDescriptionListData, JobDescriptionExtension, JobDescriptionList };
