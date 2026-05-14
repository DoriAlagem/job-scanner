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
_BASE_URL = "https://www.gotfriends.co.il"
_SEARCH_TERMS = ["python", "software engineer", "devops", "qa automation", "backend", "data"]
_REQUEST_DELAY = 1.5


def scrape() -> list[JobListing]:
    return scrape_terms(
        "gotfriends",
        lambda term: f"{_BASE_URL}/jobs/?q={term.replace(' ', '+')}",
        _parse_listings,
        _SEARCH_TERMS,
    )


def fetch_full_description(url: str) -> str | None:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        descs = soup.select("div.desc")
        # Last div.desc is the "send CV" prompt — skip it
        relevant = descs[:-1] if len(descs) > 1 else descs
        text = " ".join(d.get_text(separator=" ", strip=True) for d in relevant)
        return text[:4000] if len(text) > 50 else None
    except Exception as e:
        logger.debug("gotfriends: failed to fetch full description for %s: %s", url, e)
        return None


def _parse_listings(html: str, seen_urls: set[str]) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select("div.item"):
        try:
            listing = _parse_item(item)
            if listing and listing.url not in seen_urls:
                seen_urls.add(listing.url)
                results.append(listing)
        except Exception as e:
            logger.debug("gotfriends: failed to parse item: %s", e)

    return results


def _parse_item(item) -> JobListing | None:
    title_el = item.select_one("h2.title")
    link_el = item.select_one("a.position")
    if not title_el or not link_el:
        return None

    title = title_el.get_text(strip=True)
    href = link_el.get("href", "")
    url = _BASE_URL + href if href.startswith("/") else href

    location_el = item.select_one("section.info span.info-data")
    location = location_el.get_text(strip=True) if location_el else "Israel"

    # Cards include full description + requirements — join all desc divs except last (CTA)
    descs = item.select("div.desc")
    relevant = descs[:-1] if len(descs) > 1 else descs
    description = " ".join(d.get_text(separator=" ", strip=True) for d in relevant)

    return JobListing(
        title=title,
        company="Unknown",
        location=location,
        url=url,
        description=description,
        source="gotfriends",
    )
