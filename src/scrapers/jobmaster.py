import logging
import time
import requests
from bs4 import BeautifulSoup
from src.models import JobListing

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
_BASE_URL = "https://www.jobmaster.co.il"
_SEARCH_TERMS = ["python", "software engineer", "devops", "qa automation", "backend"]
_REQUEST_DELAY = 1.5


def scrape() -> list[JobListing]:
    listings: list[JobListing] = []
    seen_urls: set[str] = set()

    for term in _SEARCH_TERMS:
        try:
            url = f"{_BASE_URL}/jobs/?q={term.replace(' ', '+')}&fromSearch=1"
            response = requests.get(url, headers=_HEADERS, timeout=15)
            response.raise_for_status()
            listings.extend(_parse_listings(response.text, seen_urls))
            time.sleep(_REQUEST_DELAY)
        except Exception as e:
            logger.warning("jobmaster: failed to scrape %r: %s", term, e)

    return listings


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select(".JobItemRight"):
        try:
            listing = _parse_item(item)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("jobmaster: failed to parse item: %s", e)

    return results


def _parse_item(item) -> JobListing | None:
    title_el = item.select_one("a.CardHeader")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    url = _BASE_URL + href if href.startswith("/") else href

    company_el = item.select_one(".CompanyNameLink span")
    company = company_el.get_text(strip=True) if company_el else "Unknown"

    location_el = item.select_one(".jobLocation span")
    location = location_el.get_text(strip=True) if location_el else "Israel"

    desc_el = item.select_one(".jobShortDescription")
    description = desc_el.get_text(strip=True) if desc_el else ""

    return JobListing(
        title=title,
        company=company,
        location=location,
        url=url,
        description=description,
        source="jobmaster",
    )
