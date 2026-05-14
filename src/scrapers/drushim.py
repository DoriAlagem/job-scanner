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
_BASE_URL = "https://www.drushim.co.il"
# cat5 = hi-tech general, cat6 = hi-tech software
_CATEGORIES = ["cat5", "cat6"]
_REQUEST_DELAY = 1.5  # seconds between requests


def scrape() -> list[JobListing]:
    listings: list[JobListing] = []
    seen_urls: set[str] = set()

    for category in _CATEGORIES:
        try:
            url = f"{_BASE_URL}/jobs/{category}/"
            response = requests.get(url, headers=_HEADERS, timeout=15)
            response.raise_for_status()
            listings.extend(_parse_listings(response.text, seen_urls))
            time.sleep(_REQUEST_DELAY)
        except Exception as e:
            logger.warning("drushim: failed to scrape %s: %s", category, e)

    return listings


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select(".job-item"):
        try:
            listing = _parse_item(item)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("drushim: failed to parse item: %s", e)

    return results


def _parse_item(item) -> JobListing | None:
    title_el = item.select_one("h3 .job-url")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    company_el = item.select_one(".font-weight-medium.underline")
    company = company_el.get_text(strip=True) if company_el else "Unknown"

    link_el = item.select_one('a[href*="/job/"]')
    if not link_el:
        return None
    href = link_el.get("href", "")
    url = _BASE_URL + href if href.startswith("/") else href

    desc_el = item.select_one(".job-intro p")
    description = desc_el.get_text(strip=True) if desc_el else ""

    spans = [s.get_text(strip=True) for s in item.select(".display-18")]
    location_candidates = [
        s.rstrip("|")
        for s in spans
        if s and s != "|" and "שנים" not in s and "משרה" not in s
        and "לפני" not in s and "לצפייה" not in s and "+" not in s
    ]
    location = location_candidates[0] if location_candidates else "Israel"

    return JobListing(
        title=title,
        company=company,
        location=location,
        url=url,
        description=description,
        source="drushim",
    )
