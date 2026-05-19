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
_REQUEST_DELAY = 1.5

# Category position IDs from SearchEngineData.js — text-search (q=) is processed
# client-side by Angular and is ignored in the server-rendered HTML, so we scrape
# by category instead.
_CATEGORIES = [
    1694,  # מתכנת Python
    1759,  # מתכנת Backend
    1183,  # Backend Engineer
    432,   # QA תוכנה
    434,   # מהנדס בדיקות
    1532,  # בדיקות ידניות
    1533,  # בדיקות אוטומטיות
    1984,  # QA Automation Infrastructure
    2011,  # QA אוטומציה
    1706,  # איש DevOps
    2028,  # מהנדס/ת דאטה
    1779,  # NLP/Machine Learning
    2006,  # AI Engineer
]


def scrape(terms: list[str] | None = None) -> list[JobListing]:
    # alljobs ignores `terms` — it scrapes by hi-tech category instead.
    # The q= text-search parameter is handled client-side by Angular and
    # returns the same featured listings regardless of query when fetched statically.
    return scrape_terms(
        "alljobs",
        lambda cat: f"{_BASE_URL}/SearchResultsGuest.aspx?page=1&position={cat}&type=4&source=&duration=&region=&city=0&pos=1",
        _parse_listings,
        [str(c) for c in _CATEGORIES],
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
