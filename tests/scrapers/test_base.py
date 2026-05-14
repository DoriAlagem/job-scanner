from unittest.mock import MagicMock, patch
from src.scrapers.base import scrape_terms
from src.models import JobListing


def _make_listing(url: str) -> JobListing:
    return JobListing(title="T", company="C", location="L", url=url, description="", source="test")


def _html_parser(html: str, seen_urls: set) -> list[JobListing]:
    listing = _make_listing(html)  # use html string as URL for simplicity
    if listing.url in seen_urls:
        return []
    seen_urls.add(listing.url)
    return [listing]


def test_skips_term_and_continues_on_request_error():
    terms = ["ok-term", "bad-term", "ok-term-2"]

    def build_url(term):
        return term

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.text = "ok-term"

    def fake_get(url, **kwargs):
        if url == "bad-term":
            raise ConnectionError("network error")
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.text = url
        return r

    with patch("src.scrapers.base.requests.get", side_effect=fake_get), \
         patch("src.scrapers.base.time.sleep"):
        results = scrape_terms("test", build_url, _html_parser, terms)

    assert len(results) == 2
    assert all(r.url != "bad-term" for r in results)


def test_deduplicates_urls_across_terms():
    # Two terms that return the same URL
    terms = ["term-a", "term-b"]

    def build_url(term):
        return "same-url"

    call_count = 0

    def parse(html, seen_urls):
        nonlocal call_count
        call_count += 1
        listing = _make_listing("same-url")
        if listing.url in seen_urls:
            return []
        seen_urls.add(listing.url)
        return [listing]

    with patch("src.scrapers.base.requests.get") as mock_get, \
         patch("src.scrapers.base.time.sleep"):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.text = "same-url"
        mock_get.return_value = mock_resp

        results = scrape_terms("test", build_url, parse, terms)

    assert len(results) == 1
    assert call_count == 2  # parse called for each term, but dedup happens inside parse
