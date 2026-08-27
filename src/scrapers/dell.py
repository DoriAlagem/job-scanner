import json
import logging
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
    ),
    "Accept": "application/json",
}
_REQUEST_DELAY = 1.5
# Dell's careers site runs on Oracle Fusion Cloud Recruiting. The candidate
# widget calls this REST API directly (no auth required); the site itself
# is a JS SPA shell so job pages can't be scraped statically.
_API_BASE = "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
_DETAIL_API_BASE = "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
_JOB_URL_BASE = "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/CX_1/job/"
_SITE_NUMBER = "CX_1"


def scrape(terms: list[str]) -> list[JobListing]:
    def _build_url(term: str) -> str:
        finder = f"findReqs;siteNumber={_SITE_NUMBER},keyword={term},location=Israel,limit=25"
        return f"{_API_BASE}?{urlencode({'onlyData': 'true', 'expand': 'requisitionList', 'finder': finder})}"

    return scrape_terms(
        "dell",
        _build_url,
        _parse_listings,
        terms,
        request_delay=_REQUEST_DELAY,
        headers=_HEADERS,
    )


def fetch_full_description(url: str) -> str | None:
    try:
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        finder = f"ById;Id={job_id},siteNumber={_SITE_NUMBER}"
        params = {"onlyData": "true", "finder": finder}
        response = requests.get(_DETAIL_API_BASE, params=params, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return None
        text = _detail_text(items[0])
        return text[:4000] if len(text) > 100 else None
    except Exception as e:
        logger.debug("dell: failed to fetch full description for %s: %s", url, e)
        return None


def _detail_text(detail: dict) -> str:
    parts = [
        BeautifulSoup(detail[field], "html.parser").get_text(separator=" ", strip=True)
        for field in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")
        if detail.get(field)
    ]
    return "\n\n".join(parts)


def _parse_listings(text: str, seen_urls: set[str]) -> list[JobListing]:
    results = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("dell: failed to parse API response: %s", e)
        return results

    for item in data.get("items", []):
        for req in item.get("requisitionList", []):
            try:
                listing = _parse_req(req)
                if listing and listing.url not in seen_urls:
                    seen_urls.add(listing.url)
                    results.append(listing)
            except Exception as e:
                logger.debug("dell: failed to parse item: %s", e)
    return results


def _parse_req(req: dict) -> JobListing | None:
    job_id = req.get("Id")
    title = req.get("Title")
    if not job_id or not title:
        return None
    return JobListing(
        title=title,
        company="Dell",
        location=req.get("PrimaryLocation") or "Israel",
        url=f"{_JOB_URL_BASE}{job_id}",
        description=req.get("ShortDescriptionStr") or "",
        source="dell",
    )
