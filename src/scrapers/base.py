import logging
import time
from typing import Callable, Protocol

import requests
from src.models import JobListing

logger = logging.getLogger(__name__)


class Scraper(Protocol):
    """Every job-board scraper must conform to this interface.

    Used by the orchestrator's `_SCRAPERS` registry. The `Protocol` lets us
    type-check without forcing inheritance.
    """

    def scrape(self, terms: list[str]) -> list[JobListing]:
        """Fetch listings for the given search terms; per-term failures are swallowed.
        Scrapers that scrape by category (e.g. drushim) may ignore `terms`."""
        ...

    def fetch_full_description(self, url: str) -> str | None:
        """Fetch the full description for a given listing URL, or None if unavailable."""
        ...

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_terms(
    name: str,
    build_url: Callable[[str], str],
    parse_html: Callable[[str, set[str]], list[JobListing]],
    terms: list[str],
    request_delay: float = 1.5,
    headers: dict | None = None,
) -> list[JobListing]:
    """Shared scrape loop used by all scrapers: iterate terms → GET → parse → dedup → sleep."""
    if headers is None:
        headers = _DEFAULT_HEADERS
    listings: list[JobListing] = []
    seen_urls: set[str] = set()
    for term in terms:
        try:
            response = requests.get(build_url(term), headers=headers, timeout=15)
            response.raise_for_status()
            listings.extend(parse_html(response.text, seen_urls))
            time.sleep(request_delay)
        except Exception as e:
            logger.warning("%s: failed to scrape %r: %s", name, term, e)
    return listings
