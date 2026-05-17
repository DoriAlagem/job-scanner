import logging
import time
from typing import Callable, Protocol

import requests
from requests.exceptions import ConnectionError, Timeout
from src.models import JobListing

logger = logging.getLogger(__name__)

_CONNECT_RETRIES = 3
_CONNECT_RETRY_DELAY = 5.0


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
        for attempt in range(_CONNECT_RETRIES):
            try:
                response = requests.get(build_url(term), headers=headers, timeout=15)
                response.raise_for_status()
                listings.extend(parse_html(response.text, seen_urls))
                time.sleep(request_delay)
                break
            except (ConnectionError, Timeout) as e:
                if attempt < _CONNECT_RETRIES - 1:
                    logger.warning("%s: connection error for %r (attempt %d/%d), retrying in %gs: %s",
                                   name, term, attempt + 1, _CONNECT_RETRIES, _CONNECT_RETRY_DELAY, e)
                    time.sleep(_CONNECT_RETRY_DELAY)
                else:
                    logger.warning("%s: failed to scrape %r after %d attempts: %s",
                                   name, term, _CONNECT_RETRIES, e)
            except Exception as e:
                logger.warning("%s: failed to scrape %r: %s", name, term, e)
                break
    return listings
