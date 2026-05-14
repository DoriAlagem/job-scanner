from unittest.mock import MagicMock, patch
from src.orchestrator import _scrape_all, _enrich
from src.models import JobListing


def _listing(url="https://example.com/1", source="drushim", description=""):
    return JobListing(title="Dev", company="Co", location="Tel Aviv",
                      url=url, description=description, source=source)


# --- _scrape_all ---

def test_scrape_all_combines_listings_from_all_scrapers():
    a = MagicMock()
    a.__name__ = "src.scrapers.a"
    a.scrape.return_value = [_listing("https://a.com/1")]

    b = MagicMock()
    b.__name__ = "src.scrapers.b"
    b.scrape.return_value = [_listing("https://b.com/1"), _listing("https://b.com/2")]

    result = _scrape_all([a, b])
    assert len(result) == 3


def test_scrape_all_continues_when_one_scraper_raises():
    ok = MagicMock()
    ok.__name__ = "src.scrapers.ok"
    ok.scrape.return_value = [_listing("https://ok.com/1")]

    bad = MagicMock()
    bad.__name__ = "src.scrapers.bad"
    bad.scrape.side_effect = RuntimeError("network down")

    result = _scrape_all([ok, bad])
    assert len(result) == 1
    assert result[0].url == "https://ok.com/1"


# --- _enrich ---

def test_enrich_updates_description_when_full_text_is_longer():
    listing = _listing(description="short")
    scraper = MagicMock()
    scraper.fetch_full_description.return_value = "much longer full description text"

    count = _enrich([listing], {"drushim": scraper}, delay=0)

    assert count == 1
    assert listing.description == "much longer full description text"


def test_enrich_skips_when_fetch_returns_none():
    listing = _listing(description="original")
    scraper = MagicMock()
    scraper.fetch_full_description.return_value = None

    count = _enrich([listing], {"drushim": scraper}, delay=0)

    assert count == 0
    assert listing.description == "original"


def test_enrich_skips_when_full_text_is_shorter():
    listing = _listing(description="already a long description that won't be replaced")
    scraper = MagicMock()
    scraper.fetch_full_description.return_value = "short"

    count = _enrich([listing], {"drushim": scraper}, delay=0)

    assert count == 0
    assert "already a long" in listing.description


def test_enrich_skips_listing_with_no_matching_scraper():
    listing = _listing(source="unknown_source", description="original")
    count = _enrich([listing], {}, delay=0)
    assert count == 0
    assert listing.description == "original"
