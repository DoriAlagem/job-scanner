import json
import logging
import re
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from src.scrapers.base import scrape_terms
from src.models import JobListing

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
_REQUEST_DELAY = 2.0
_BASE_URL = "https://www.google.com/about/careers/applications/jobs/results/"

# Google's careers site is a JS app, but job data for the current page is
# embedded server-side in an AF_initDataCallback block — no separate API call
# or JS execution needed.
_DATA_BLOCK_RE = re.compile(r"AF_initDataCallback\((\{.*?\})\);", re.DOTALL)
_DATA_ARRAY_RE = re.compile(r"data:(\[.*\]), sideChannel", re.DOTALL)


def scrape(terms: list[str]) -> list[JobListing]:
    def _build_url(term: str) -> str:
        return f"{_BASE_URL}?{urlencode({'location': 'Israel', 'q': term})}"

    return scrape_terms(
        "google",
        _build_url,
        _parse_listings,
        terms,
        request_delay=_REQUEST_DELAY,
        headers=_HEADERS,
    )


def fetch_full_description(url: str) -> str | None:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        jobs = _extract_jobs(response.text)
        if not jobs:
            return None
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        job = next((j for j in jobs if j[0] == job_id), jobs[0])
        text = _job_description_text(job)
        return text[:4000] if len(text) > 100 else None
    except Exception as e:
        logger.debug("google: failed to fetch full description for %s: %s", url, e)
        return None


def _extract_jobs(html: str) -> list:
    for block in _DATA_BLOCK_RE.findall(html):
        if '"ds:1"' not in block and "key: 'ds:1'" not in block:
            continue
        match = _DATA_ARRAY_RE.search(block)
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if data and isinstance(data[0], list):
            return data[0]
    return []


def _html_to_text(fragment) -> str:
    if not isinstance(fragment, list) or len(fragment) < 2 or not fragment[1]:
        return ""
    return BeautifulSoup(fragment[1], "html.parser").get_text(separator=" ", strip=True)


def _job_description_text(job: list) -> str:
    parts = [_html_to_text(job[i]) for i in (10, 3, 4, 19) if i < len(job)]
    return "\n\n".join(p for p in parts if p)


def _job_location(job: list) -> str:
    locations = job[9] if len(job) > 9 and job[9] else None
    if not locations or not locations[0]:
        return "Israel"
    return locations[0][0]


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    results = []
    for job in _extract_jobs(html):
        try:
            listing = _parse_job(job)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("google: failed to parse item: %s", e)
    return results


def _parse_job(job: list) -> JobListing | None:
    if len(job) < 8 or not job[0] or not job[1]:
        return None
    return JobListing(
        title=job[1],
        company=job[7] or "Google",
        location=_job_location(job),
        url=f"{_BASE_URL}{job[0]}",
        description=_job_description_text(job),
        source="google",
    )
