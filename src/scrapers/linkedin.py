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
_SEARCH_TERMS = ["python developer", "software engineer", "devops", "qa automation", "backend developer", "data engineer"]
_REQUEST_DELAY = 2.0
# f_TPR=r86400 = posted in last 24 hours
_BASE_URL = "https://il.linkedin.com/jobs/search"


def scrape() -> list[JobListing]:
    listings: list[JobListing] = []
    seen_urls: set[str] = set()

    for term in _SEARCH_TERMS:
        try:
            params = {
                "keywords": term,
                "location": "Israel",
                "f_TPR": "r86400",
            }
            response = requests.get(_BASE_URL, params=params, headers=_HEADERS, timeout=15)
            response.raise_for_status()
            listings.extend(_parse_listings(response.text, seen_urls))
            time.sleep(_REQUEST_DELAY)
        except Exception as e:
            logger.warning("linkedin: failed to scrape %r: %s", term, e)

    return listings


def fetch_full_description(url: str) -> str | None:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for sel in [".description__text", ".show-more-less-html__markup", "section.description"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    return text[:4000]
        return None
    except Exception as e:
        logger.debug("linkedin: failed to fetch full description for %s: %s", url, e)
        return None


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select(".job-search-card"):
        try:
            listing = _parse_item(item)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("linkedin: failed to parse item: %s", e)

    return results


def _parse_item(item) -> JobListing | None:
    title_el = item.select_one(".base-search-card__title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    company_el = item.select_one(".base-search-card__subtitle")
    company = company_el.get_text(strip=True) if company_el else "Unknown"

    location_el = item.select_one(".job-search-card__location")
    location = location_el.get_text(strip=True) if location_el else "Israel"

    link_el = item.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
    if not link_el:
        return None
    url = link_el.get("href", "").split("?")[0]  # strip tracking params

    return JobListing(
        title=title,
        company=company,
        location=location,
        url=url,
        description="",
        source="linkedin",
    )
