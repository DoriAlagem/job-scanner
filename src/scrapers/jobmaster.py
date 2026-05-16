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
_BASE_URL = "https://www.jobmaster.co.il"
_SEARCH_TERMS = ["python", "software engineer", "devops", "qa automation", "backend", "qa", "manual qa", "automation engineer", "integration", "בדיקות", "אוטומציה", "מפתח תוכנה", "בק אנד", "אינטגרציה"]
_REQUEST_DELAY = 1.5


def scrape() -> list[JobListing]:
    return scrape_terms(
        "jobmaster",
        lambda term: f"{_BASE_URL}/jobs/?q={term.replace(' ', '+')}&fromSearch=1",
        _parse_listings,
        _SEARCH_TERMS,
    )


def fetch_full_description(url: str) -> str | None:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for sel in [".JobDescriptionMain", "[class*=Description]", ".JobContent"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    return text
        return None
    except Exception as e:
        logger.debug("jobmaster: failed to fetch full description for %s: %s", url, e)
        return None


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
