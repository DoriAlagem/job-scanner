import logging
import time
import requests
from bs4 import BeautifulSoup
from src.models import JobListing

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_BASE_URL = "https://il.indeed.com"
_SEARCH_TERMS = ["python developer", "software engineer", "devops", "backend", "qa automation", "data engineer"]
_REQUEST_DELAY = 2.0


def scrape() -> list[JobListing]:
    listings: list[JobListing] = []
    seen_urls: set[str] = set()

    for term in _SEARCH_TERMS:
        try:
            url = f"{_BASE_URL}/jobs?q={term.replace(' ', '+')}&l=Israel&fromage=1"
            response = requests.get(url, headers=_HEADERS, timeout=15)
            response.raise_for_status()
            new = _parse_listings(response.text, seen_urls)
            if not new:
                logger.debug("indeed: no cards parsed for %r (may be bot-blocked)", term)
            listings.extend(new)
            time.sleep(_REQUEST_DELAY)
        except Exception as e:
            logger.warning("indeed: failed to scrape %r: %s", term, e)

    return listings


def fetch_full_description(url: str) -> str | None:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        el = soup.select_one("#jobDescriptionText")
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 50:
                return text[:4000]
        return None
    except Exception as e:
        logger.debug("indeed: failed to fetch full description for %s: %s", url, e)
        return None


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select("div.job_seen_beacon"):
        try:
            listing = _parse_item(item)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("indeed: failed to parse item: %s", e)

    return results


def _parse_item(item) -> JobListing | None:
    title_el = item.select_one("h2.jobTitle a")
    if not title_el:
        return None

    title_span = title_el.select_one("span[title]") or title_el.select_one("span")
    title = title_span.get_text(strip=True) if title_span else title_el.get_text(strip=True)

    jk = title_el.get("data-jk", "")
    if not jk:
        return None
    url = f"{_BASE_URL}/viewjob?jk={jk}"

    company_el = item.select_one("span[data-testid='company-name']")
    company = company_el.get_text(strip=True) if company_el else "Unknown"

    location_el = item.select_one("div[data-testid='text-location']")
    location = location_el.get_text(strip=True) if location_el else "Israel"

    return JobListing(
        title=title,
        company=company,
        location=location,
        url=url,
        description="",
        source="indeed",
    )
