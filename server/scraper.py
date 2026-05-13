"""DOU вакансії → синхронізація в нашу SQLite БД.

Що робить скрипт
----------------
1) Відкриває сторінку з вакансіями на jobs.dou.ua
2) Натискає кнопку "Показати ще" (XPath такий самий, як у chrome extension)
   доки вона не зникне
3) Збирає всі job urls з списку вакансій (XPath як у extension)
4) Формує `JobDescriptionList` та викликає `sync_jobs()` (локально, без HTTP)

Запуск
------
python -m server.scraper --url "https://jobs.dou.ua/vacancies/?category=Python" --headless

Примітка
--------
Selenium потребує встановленого Chrome. Драйвер підтягуємо через webdriver-manager.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from protocol.python.job import JobDescriptionExtension, JobDescriptionList
from server.jobs_sync import upsert_jobs
from backend.db.database import init_db


SHOW_MORE_XPATH = '//*[@id="vacancyListId"]/div/a'
LIST_XPATH = '//*[@id="vacancyListId"]/ul'


@dataclass(frozen=True, slots=True)
class ScrapeResult:
	clicks: int
	jobs_found: int
	synced: int
	job_ids: list[str]


def _build_driver(headless: bool) -> webdriver.Chrome:
	"""Create a Chrome WebDriver.

	Server-friendly defaults:
	- headless mode (when headless=True)
	- no-sandbox / disable-dev-shm-usage (often needed in containers/CI)

	If you run this on a server where Chrome is installed in a non-standard
	location, set:
	  CHROME_BINARY=/usr/bin/google-chrome
	"""
	options = webdriver.ChromeOptions()

	# Headless (new) is more stable with modern Chrome.
	if headless:
		options.add_argument("--headless=new")

	options.add_argument("--no-sandbox")
	options.add_argument("--disable-dev-shm-usage")
	options.add_argument("--window-size=1400,900")

	# Helpful on Linux servers; harmless elsewhere.
	options.add_argument("--disable-gpu")

	# Remote debugging can help in some server environments; only enable if asked.
	if os.getenv("CHROME_REMOTE_DEBUG") == "1":
		options.add_argument("--remote-debugging-port=9222")

	chrome_binary = os.getenv("CHROME_BINARY")
	if chrome_binary:
		options.binary_location = chrome_binary
	elif sys.platform.startswith("linux") and os.path.exists("/usr/bin/google-chrome"):
		# Common default on Linux servers.
		options.binary_location = "/usr/bin/google-chrome"

	service = Service(ChromeDriverManager().install())
	return webdriver.Chrome(service=service, options=options)


def _click_show_more_until_gone(driver: webdriver.Chrome, *, max_clicks: int = 200, sleep_sec: float = 1.0) -> int:
	"""Click the 'show more' button until it's not found or not visible."""
	clicks = 0
	for _ in range(max_clicks):
		try:
			btn = driver.find_element(By.XPATH, SHOW_MORE_XPATH)
		except NoSuchElementException:
			break

		try:
			if not btn.is_displayed():
				break
			# Scroll to button and click
			driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
			time.sleep(0.2)
			btn.click()
			clicks += 1

			# Like the extension: scroll down a bit after clicking
			driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
			time.sleep(sleep_sec)
		except (StaleElementReferenceException, Exception):
			# DOM updates are common; retry next loop iteration
			time.sleep(0.5)
			continue
	return clicks


def _iter_jobs(driver: webdriver.Chrome) -> Iterable[JobDescriptionExtension]:
	"""Extract jobs from the list container using the same anchor strategy as the extension."""
	list_el = driver.find_element(By.XPATH, LIST_XPATH)
	li_items = list_el.find_elements(By.XPATH, "./li")

	seen: set[str] = set()
	for li in li_items:
		# Extension logic: prefer link inside `div:nth-of-type(2)` if present.
		link = None
		try:
			details_block = li.find_element(By.CSS_SELECTOR, "div:nth-of-type(2)")
			links = details_block.find_elements(By.CSS_SELECTOR, "a[href]")
			link = links[0] if links else None
		except Exception:
			link = None

		if link is None:
			links = li.find_elements(By.CSS_SELECTOR, "a[href]")
			link = links[0] if links else None

		if link is None:
			continue

		href = (link.get_attribute("href") or "").strip()
		title = (link.text or "").strip()
		if not href or not title:
			continue

		# Basic de-dup
		if href in seen:
			continue
		seen.add(href)
		yield JobDescriptionExtension(job_title=title, source_url=href)


def scrape_and_sync(url: str, *, headless: bool = True, wait_sec: int = 20, user_id: int = 1) -> ScrapeResult:
	init_db()

	driver = _build_driver(headless=headless)
	try:
		driver.get(url)

		# Wait until the list container exists.
		WebDriverWait(driver, wait_sec).until(EC.presence_of_element_located((By.XPATH, LIST_XPATH)))

		clicks = _click_show_more_until_gone(driver)
		jobs = list(_iter_jobs(driver))
		job_list = JobDescriptionList(jobs=jobs)
		job_ids = upsert_jobs(job_list)
		return ScrapeResult(clicks=clicks, jobs_found=len(jobs), synced=int(len(job_ids)), job_ids=job_ids)
	finally:
		driver.quit()


def main() -> None:
	p = argparse.ArgumentParser(description="Scrape DOU вакансії та синхронізувати в SQLite")
	p.add_argument(
		"--url",
		default="https://jobs.dou.ua/vacancies/?category=Python",
		help="DOU vacancies page URL",
	)
	p.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
	args = p.parse_args()

	res = scrape_and_sync(args.url, headless=args.headless)
	print(f"Clicked 'show more': {res.clicks} time(s)")
	print(f"Jobs found: {res.jobs_found}")
	print(f"Synced to DB: {res.synced}")


if __name__ == "__main__":
	main()
