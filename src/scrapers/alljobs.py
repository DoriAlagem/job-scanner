import logging
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
_BASE_URL = "https://www.alljobs.co.il"
_SEARCH_TERMS = ["python", "software engineer", "devops", "qa automation", "backend"]
_REQUEST_DELAY = 1.5


def scrape() -> list[JobListing]:
    return scrape_terms(
        "alljobs",
        lambda term: f"{_BASE_URL}/SearchResultsGuest.aspx?pos=1&type=4&city=0&q={term.replace(' ', '+')}",
        _parse_listings,
        _SEARCH_TERMS,
    )


def fetch_full_description(url: str) -> str | None:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # alljobs job pages have a free-form structure — pull all visible text and trim
        full_text = soup.get_text(separator=" ", strip=True)
        # Cut starting from תיאור (description) marker if present
        marker_idx = full_text.find("תיאור")
        if marker_idx > 0:
            full_text = full_text[marker_idx:]
        # Limit to ~4000 chars to keep prompt size reasonable
        return full_text[:4000] if len(full_text) > 100 else None
    except Exception as e:
        logger.debug("alljobs: failed to fetch full description for %s: %s", url, e)
        return None


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select(".job-box"):
        try:
            listing = _parse_item(item)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("alljobs: failed to parse item: %s", e)

    return results


def _parse_item(item) -> JobListing | None:
    title_el = item.select_one("a[href*='UploadSingle']")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    url = _BASE_URL + href if href.startswith("/") else href

    company_el = item.select_one(".job-content-top-title-highlight .T14")
    company = company_el.get_text(strip=True) if company_el else "Unknown"

    location_el = item.select_one(".job-content-top-location")
    if location_el:
        location_text = location_el.get_text(separator=" ", strip=True)
        location = location_text.replace("מיקום המשרה:", "").replace("מיקום המשרה :", "").strip()
        if "מספר מקומות" in location:
            location = "מספר מקומות"
    else:
        location = "Israel"

    desc_el = item.select_one(".job-content-top-acord")
    description = desc_el.get_text(strip=True) if desc_el else ""

    return JobListing(
        title=title,
        company=company,
        location=location,
        url=url,
        description=description,
        source="alljobs",
    )
