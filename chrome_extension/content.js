(() => {
  // protocol/js/job.ts
  var JobDescriptionExtension = class _JobDescriptionExtension {
    constructor({ job_title, source_url }) {
      this.job_title = String(job_title);
      this.source_url = String(source_url);
    }
    static fromDict(data) {
      return new _JobDescriptionExtension({
        job_title: data.job_title,
        source_url: data.source_url
      });
    }
    toDict() {
      return {
        job_title: this.job_title,
        source_url: this.source_url
      };
    }
  };
  var JobDescriptionList = class _JobDescriptionList {
    constructor(jobs) {
      this.jobs = jobs;
    }
    static fromList(data) {
      if (!Array.isArray(data)) {
        throw new Error("Expected an array of job descriptions");
      }
      return new _JobDescriptionList(data.map((item) => JobDescriptionExtension.fromDict(item)));
    }
    static fromDict(data) {
      if (!("jobs" in data)) {
        throw new Error("Expected an object with 'jobs' key");
      }
      return _JobDescriptionList.fromList(data.jobs);
    }
    static fromJson(data) {
      const parsed = JSON.parse(data);
      if (typeof parsed === "object" && parsed !== null && "jobs" in parsed) {
        return _JobDescriptionList.fromDict(parsed);
      }
      if (Array.isArray(parsed)) {
        return _JobDescriptionList.fromList(parsed);
      }
      throw new Error("Expected a JSON object with 'jobs' key or a JSON array");
    }
    toList() {
      return this.jobs.map((job) => job.toDict());
    }
    toDict() {
      return { jobs: this.toList() };
    }
    toJson() {
      return JSON.stringify(this.toDict());
    }
  };

  // chrome_extension/content.src.ts
  var isRunning = false;
  var intervalId = null;
  var clickCount = 0;
  function getTabId() {
    let tabId = sessionStorage.getItem("indeedNavigatorTabId");
    if (!tabId) {
      tabId = "tab_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
      sessionStorage.setItem("indeedNavigatorTabId", tabId);
      console.log("Created new tab ID:", tabId);
    }
    return tabId;
  }
  var TAB_ID = getTabId();
  function createControlPanel() {
    if (document.getElementById("indeed-navigator-panel")) {
      return;
    }
    const panel = document.createElement("div");
    panel.id = "indeed-navigator-panel";
    panel.innerHTML = `
    <div class="nav-panel-header">
      <span>Dou Navigator</span>
      <button id="nav-minimize" class="nav-btn-minimize">_</button>
    </div>
    <div class="nav-panel-content">
      <div class="nav-status">Status: <span id="nav-status">Stopped</span></div>
      <button id="nav-start" class="nav-btn nav-btn-start">Start</button>
      <button id="nav-stop" class="nav-btn nav-btn-stop" disabled>Stop</button>
      <div class="nav-info">
        <small>Clicks: <span id="nav-clicks">0</span></small>
      </div>
    </div>
  `;
    document.body.appendChild(panel);
    document.getElementById("nav-start").addEventListener("click", startNavigation);
    document.getElementById("nav-stop").addEventListener("click", stopNavigation);
    document.getElementById("nav-minimize").addEventListener("click", toggleMinimize);
    console.log("Dou Navigator panel created");
    loadState();
    console.log("Control panel initialized and state loaded");
  }
  function toggleMinimize() {
    const panel = document.getElementById("indeed-navigator-panel");
    const content = panel.querySelector(".nav-panel-content");
    const minimizeBtn = document.getElementById("nav-minimize");
    if (content.style.display === "none") {
      content.style.display = "block";
      minimizeBtn.textContent = "_";
    } else {
      content.style.display = "none";
      minimizeBtn.textContent = "+";
    }
  }
  function startNavigation() {
    if (isRunning)
      return;
    isRunning = true;
    updateStatus("Running", "running");
    document.getElementById("nav-start").disabled = true;
    document.getElementById("nav-stop").disabled = false;
    console.log("Starting navigation...");
    saveState();
    intervalId = setInterval(openMoreJobs, 5e3);
  }
  function stopNavigation() {
    if (!isRunning)
      return;
    isRunning = false;
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
    updateStatus("Stopped", "stopped");
    document.getElementById("nav-start").disabled = false;
    document.getElementById("nav-stop").disabled = true;
    saveState();
    console.log("Navigation stopped");
  }
  function updateStatus(text, className) {
    const statusEl = document.getElementById("nav-status");
    statusEl.textContent = text;
    statusEl.className = className;
  }
  function saveState() {
    const storageKey = `indeedNavigator_${TAB_ID}`;
    chrome.storage.local.set({
      [storageKey]: {
        isRunning,
        clickCount,
        timestamp: Date.now(),
        tabId: TAB_ID
      }
    }, () => {
      console.log("State saved for tab:", TAB_ID, { isRunning, clickCount });
    });
  }
  function loadState() {
    const storageKey = `indeedNavigator_${TAB_ID}`;
    chrome.storage.local.get([storageKey], (result) => {
      if (result[storageKey]) {
        const savedState = result[storageKey];
        const now = Date.now();
        const savedTime = savedState.timestamp || 0;
        const fiveMinutes = 5 * 60 * 1e3;
        if (now - savedTime > fiveMinutes) {
          console.log("State expired (older than 5 minutes), clearing...");
          chrome.storage.local.remove(storageKey);
          return;
        }
        clickCount = savedState.clickCount || 0;
        document.getElementById("nav-clicks").textContent = clickCount;
        console.log("State loaded for tab:", TAB_ID, savedState, `Age: ${Math.round((now - savedTime) / 1e3)}s`);
        if (savedState.isRunning) {
          updateStatus("Resuming in 5s...", "running");
          console.log("Will resume navigation in 5 seconds...");
          setTimeout(() => {
            startNavigation();
            console.log("Navigation resumed after page reload");
          }, 5e3);
        }
      }
    });
    cleanupOldStates();
  }
  function cleanupOldStates() {
    chrome.storage.local.get(null, (items) => {
      const now = Date.now();
      const fiveMinutes = 5 * 60 * 1e3;
      const keysToRemove = [];
      for (const key in items) {
        if (key.startsWith("indeedNavigator_")) {
          const state = items[key];
          if (state.timestamp && now - state.timestamp > fiveMinutes) {
            keysToRemove.push(key);
          }
        }
      }
      if (keysToRemove.length > 0) {
        chrome.storage.local.remove(keysToRemove, () => {
          console.log("Cleaned up expired states:", keysToRemove.length);
        });
      }
    });
  }
  var API_BASE = "http://localhost:8000";
  async function syncJobsToApi() {
    const jobs = getAllJobs();
    if (!jobs.length) {
      console.warn("No jobs to sync");
      return;
    }
    const jobList = JobDescriptionList.fromList(jobs);
    console.log("Payload to sync:", jobList.toJson());
    try {
      const res = await fetch(`${API_BASE}/api/jobs/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jobList.toJson()
      });
      if (!res.ok)
        throw new Error(`Sync failed: ${res.status} ${res.statusText}`);
      const data = await res.json();
      console.log(`Synced ${data.count} jobs to API`);
      updateStatus(`Synced ${data.count} jobs`, "stopped");
    } catch (err) {
      console.error("API sync error:", err);
      updateStatus("Sync failed", "error");
    }
  }
  function getAllJobs() {
    const xpath = '//*[@id="vacancyListId"]/ul';
    const listElement = getElementByXPath(xpath);
    if (!listElement) {
      console.warn("Job list container not found:", xpath);
      return [];
    }
    const jobs = Array.from(listElement.children).map((jobElement) => {
      const detailsBlock = jobElement.querySelector("div:nth-of-type(2)") || jobElement;
      const link = detailsBlock.querySelector("a[href]") || jobElement.querySelector("a[href]");
      const job_title = (link?.textContent || detailsBlock.textContent || "").trim();
      return {
        job_title,
        source_url: link ? link.href : ""
      };
    }).filter((job) => job.job_title && job.source_url);
    console.log("Collected jobs:", jobs.length, jobs);
    return jobs;
  }
  function openMoreJobs() {
    try {
      const xpath = '//*[@id="vacancyListId"]/div/a';
      const element = getElementByXPath(xpath);
      if (element) {
        const isHidden = element.style.display === "none" || window.getComputedStyle(element).display === "none";
        if (isHidden) {
          console.warn("Target element is hidden (display: none), stopping navigation.");
          syncJobsToApi();
          updateStatus("No more jobs", "stopped");
          stopNavigation();
          return;
        }
        element.click();
        clickCount++;
        document.getElementById("nav-clicks").textContent = clickCount;
        saveState();
        console.log(`Clicked element ${clickCount} times`);
        setTimeout(() => {
          window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
        }, 1e3);
      } else {
        console.warn("Element not found at XPath:", xpath);
        const nextButton = findNextButton();
        if (nextButton) {
          nextButton.click();
          clickCount++;
          document.getElementById("nav-clicks").textContent = clickCount;
          saveState();
          updateStatus("Running (alt method)", "running");
          console.log("Clicked next button (alternative method)");
        } else {
          console.warn("No clickable element found, stopping navigation.");
          syncJobsToApi();
          updateStatus("Element not found", "error");
          stopNavigation();
        }
      }
    } catch (error) {
      console.error("Error during navigation:", error);
      updateStatus("Error", "error");
    }
  }
  function getElementByXPath(xpath) {
    return document.evaluate(
      xpath,
      document,
      null,
      XPathResult.FIRST_ORDERED_NODE_TYPE,
      null
    ).singleNodeValue;
  }
  function findNextButton() {
    const selectors = [
      'a[aria-label*="Next"]',
      'button[aria-label*="Next"]',
      'a[data-testid*="pagination-page-next"]',
      'nav[role="navigation"] a:last-child',
      "ul.pagination li:last-child a"
    ];
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element)
        return element;
    }
    return null;
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createControlPanel);
  } else {
    createControlPanel();
  }
  window.addEventListener("beforeunload", () => {
    if (isRunning) {
      stopNavigation();
    }
  });
})();
